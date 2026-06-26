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
    from app import config

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


def test_login_failure_is_audited(client):
    _setup(client)
    client.post("/api/logout")
    client.post("/api/login", json={"username": "nadim", "password": "no"})
    # Re-login to read the audit log through an authed connection.
    client.post("/api/login", json={"username": "nadim", "password": "hunter2"})
    from app import storage, account
    key = account.authenticate("nadim", "hunter2")
    conn = storage.connect(key)
    events = [r["event_type"] for r in conn.execute("SELECT event_type FROM audit_log").fetchall()]
    assert "LOGIN_FAIL" in events
    assert "SETUP" in events
    conn.close()
