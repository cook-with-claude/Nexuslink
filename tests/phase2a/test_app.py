import pytest
from app import create_app


@pytest.fixture()
def client(app_data_dir):
    app = create_app()
    app.config.update(TESTING=True)
    return app.test_client()


def test_health_is_public(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.get_json()["data"]["status"] == "ok"


def test_status_reports_no_account_initially(client):
    r = client.get("/api/status")
    body = r.get_json()
    assert body["data"]["account_exists"] is False
    assert body["data"]["authenticated"] is False


def test_unknown_route_returns_json_envelope(client):
    r = client.get("/api/does-not-exist")
    assert r.status_code == 404
    assert r.get_json()["ok"] is False
