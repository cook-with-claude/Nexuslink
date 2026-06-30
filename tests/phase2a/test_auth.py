import pytest
from app import create_app


@pytest.fixture()
def client(app_data_dir):
    app = create_app()
    app.config.update(TESTING=True)
    return app.test_client()


def _setup(client, u="nadim", p="hunter2"):
    return client.post("/api/setup", json={"username": u, "password": p})


def test_setup_then_second_setup_conflicts(client):
    assert _setup(client).status_code == 201
    assert _setup(client).status_code == 409


def test_protected_route_requires_login(client):
    _setup(client)
    client.post("/api/logout")
    r = client.post("/api/logout")
    assert r.status_code == 401


def test_login_good_and_bad(client):
    _setup(client)
    client.post("/api/logout")
    assert client.post("/api/login", json={"username": "nadim", "password": "hunter2"}).status_code == 200
    client.post("/api/logout")
    assert client.post("/api/login", json={"username": "nadim", "password": "no"}).status_code == 401


def test_login_malformed_auth_sidecar_is_401(client):
    _setup(client)
    client.post("/api/logout")
    from app.infra import config

    config.auth_path().write_text("{not json", encoding="utf-8")
    r = client.post("/api/login", json={"username": "nadim", "password": "hunter2"})

    assert r.status_code == 401
    assert r.get_json()["error"]["code"] == "UNAUTHENTICATED"


def test_change_password_flow(client):
    _setup(client)
    assert client.post("/api/change-password",
                       json={"old_password": "WRONG", "new_password": "newpass9"}).status_code == 401
    assert client.post("/api/change-password",
                       json={"old_password": "hunter2", "new_password": "newpass9"}).status_code == 200
    client.post("/api/logout")
    assert client.post("/api/login", json={"username": "nadim", "password": "newpass9"}).status_code == 200


def test_login_failure_recorded_without_any_success(client):
    """A failed login is recorded durably to the sidecar even when no successful
    login ever follows -- the case the old in-memory buffer silently dropped."""
    import json
    from datetime import datetime

    from app.audit import log as audit
    from app.infra import config

    _setup(client)
    client.post("/api/logout")
    # Two bad attempts, never a success after them.
    client.post("/api/login", json={"username": "nadim", "password": "no"})
    client.post("/api/login", json={"username": "mallory", "password": "no"})

    path = config.app_data_dir() / audit.FAILED_LOGIN_FILE
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [r["username"] for r in records] == ["nadim", "mallory"]
    assert all(r["event_type"] == "LOGIN_FAIL" for r in records)
    # Timestamp is the failure time (parseable ISO-8601), not a later flush time.
    assert all(datetime.fromisoformat(r["ts"]) for r in records)


def test_successful_login_does_not_write_login_fail_to_db(client):
    """The encrypted audit_log no longer carries LOGIN_FAIL rows (they live in the
    sidecar); a clean login records only SETUP + LOGIN_SUCCESS."""
    from app.auth import account
    from app.infra import storage

    _setup(client)
    client.post("/api/logout")
    client.post("/api/login", json={"username": "nadim", "password": "no"})
    client.post("/api/login", json={"username": "nadim", "password": "hunter2"})

    key = account.authenticate("nadim", "hunter2")
    conn = storage.connect(key)
    events = [r["event_type"] for r in conn.execute("SELECT event_type FROM audit_log").fetchall()]
    conn.close()
    assert "SETUP" in events
    assert "LOGIN_SUCCESS" in events
    assert "LOGIN_FAIL" not in events


def test_setup_long_password_returns_400(client):
    """bcrypt rejects > 72-byte passwords; setup must return a clean 400, not 500."""
    r = _setup(client, p="x" * 73)
    assert r.status_code == 400
    assert r.get_json()["error"]["code"] == "BAD_REQUEST"
    # No account was created, so a normal short-password setup still works.
    assert _setup(client).status_code == 201


def test_change_password_long_new_returns_400(client):
    _setup(client)
    r = client.post("/api/change-password",
                    json={"old_password": "hunter2", "new_password": "y" * 73})
    assert r.status_code == 400
    assert r.get_json()["error"]["code"] == "BAD_REQUEST"
    # The original password still works -- the change was rejected, not half-applied.
    client.post("/api/logout")
    assert client.post("/api/login",
                       json={"username": "nadim", "password": "hunter2"}).status_code == 200
