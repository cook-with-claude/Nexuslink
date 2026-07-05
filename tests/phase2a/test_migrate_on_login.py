"""Increment 3.1: get_db() runs migrations on every login (ADR 0002 activation).

Driven through the real app factory + /api/setup, which leaves the client
authenticated with the server DB_KEY in app.config (identity moved to the
per-session cookie in 3.2a), exactly like the transaction-semantics tests.
"""

import pytest
from flask import g

from app import create_app
from app.api import guards
from app.infra import migrations, storage

_LATEST = migrations.MIGRATIONS[-1][0]


@pytest.fixture()
def client(app_data_dir):
    app = create_app()
    app.config.update(TESTING=True)
    c = app.test_client()
    c.post("/api/setup", json={"username": "nadim", "password": "hunter2"})
    return c


def _open_raw(client):
    """A direct SQLCipher connection to the same DB the app uses, via the
    in-memory key setup left in app.config."""
    key = client.application.config["DB_KEY"]
    return storage.connect(key)


def test_login_auto_upgrades_a_v0_database(client):
    # Simulate a pre-versioning install: valid baseline schema, version reset to 0.
    conn = _open_raw(client)
    conn.execute("PRAGMA user_version = 0")
    conn.commit()
    conn.close()

    # Any authenticated request opens a connection via get_db() -> should migrate.
    resp = client.get("/api/datasets")
    assert resp.status_code == 200

    conn = _open_raw(client)
    assert migrations.current_version(conn) == _LATEST
    conn.close()


def test_login_on_current_db_is_a_noop(client):
    # Fresh setup already stamped the DB to _LATEST. A normal request must still
    # work and leave the version exactly where it was.
    assert client.get("/api/datasets").status_code == 200

    conn = _open_raw(client)
    assert migrations.current_version(conn) == _LATEST
    conn.close()


def test_login_against_too_new_db_fails_closed(client):
    conn = _open_raw(client)
    conn.execute(f"PRAGMA user_version = {_LATEST + 5}")
    conn.commit()
    conn.close()

    # get_db() -> migrate() raises SchemaTooNewError; TESTING=True surfaces it.
    with pytest.raises(migrations.SchemaTooNewError):
        client.get("/api/datasets")


def test_get_db_closes_connection_when_migrate_raises(client, monkeypatch):
    """If migrate() raises, get_db() must close the just-opened connection (no leak)
    and not cache it in g. Regression guard for the try/except in get_db()."""
    closed = []

    class _FakeConn:
        def close(self):
            closed.append(True)

    def _raise(conn):
        raise migrations.SchemaTooNewError("boom")

    # guards holds the infra modules by reference, so patching the attributes
    # is what get_db() resolves at call time.
    monkeypatch.setattr(guards.storage, "connect", lambda key: _FakeConn())
    monkeypatch.setattr(guards.migrations, "migrate", _raise)

    app = client.application  # DB_KEY was populated by /api/setup in the fixture
    with app.app_context():
        with pytest.raises(migrations.SchemaTooNewError):
            guards.get_db()
        assert closed == [True]   # the opened connection was closed on the raise path
        assert "db" not in g      # nothing was cached for the request
