"""Increment 3.1: get_db() runs migrations on every login (ADR 0002 activation).

Driven through the real app factory + /api/setup, which leaves the client
authenticated with DB_KEY/USERNAME populated in app.config, exactly like the
transaction-semantics tests.
"""

import pytest

from app import create_app
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
