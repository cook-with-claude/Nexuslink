"""Increment 3.2b-1: fail-closed lock gate (503 until the master key is unlocked)."""
import pytest

from app import create_app


@pytest.fixture()
def locked_client(app_data_dir):
    app = create_app()
    app.config.update(TESTING=True)   # DB_KEY stays None -> server locked
    return app.test_client()


@pytest.fixture()
def unlocked_client(app_data_dir, bootstrap_key):
    app = create_app()
    app.config.update(TESTING=True, DB_KEY=bootstrap_key)
    return app.test_client()


def test_locked_server_503s_api_routes(locked_client):
    r = locked_client.get("/api/datasets")
    assert r.status_code == 503
    assert r.get_json()["error"]["code"] == "LOCKED"


def test_locked_server_allows_health_and_status(locked_client):
    assert locked_client.get("/api/health").status_code == 200
    body = locked_client.get("/api/status").get_json()["data"]
    assert body["locked"] is True


def test_unlocked_server_reports_not_locked_and_serves_api(unlocked_client):
    body = unlocked_client.get("/api/status").get_json()["data"]
    assert body["locked"] is False
    # An authed area route now reaches login_required (401), not the lock gate (503).
    assert unlocked_client.get("/api/datasets").status_code == 401
