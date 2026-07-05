import io

import pytest

from app import create_app


@pytest.fixture()
def client(app_data_dir, bootstrap_key):
    app = create_app()
    app.config.update(TESTING=True, DB_KEY=bootstrap_key)
    c = app.test_client()
    c.post("/api/setup", json={"username": "nadim", "password": "hunter2"})
    return c


@pytest.fixture()
def target_id(client, sample_xlsx):
    with open(sample_xlsx, "rb") as fh:
        data = {"name": "d", "file": (io.BytesIO(fh.read()), "sample.xlsx")}
    ds = client.post("/api/imports", data=data,
                     content_type="multipart/form-data").get_json()["data"]["dataset_id"]
    return client.post("/api/targets", json={"name": "A", "dataset_id": ds,
                       "phone_number": "01000001"}).get_json()["data"]["id"]


def test_analyze_returns_full_shape_and_persists(client, target_id):
    r = client.post(f"/api/targets/{target_id}/analyze")
    assert r.status_code == 200
    data = r.get_json()["data"]
    # User A: clean commuter -> Hamra home, High, full gate trace present.
    assert data["home"]["area"] == "Hamra"
    assert data["home"]["confidence"] == "High"
    assert set(data["home"]["gates"]) == {"N", "share", "closeness", "density"}
    assert data["frequent_contacts"]
    # Result is persisted and retrievable.
    got = client.get(f"/api/targets/{target_id}/result")
    assert got.status_code == 200
    assert got.get_json()["data"]["home"]["area"] == "Hamra"


def test_result_404_before_any_analysis(client, target_id):
    assert client.get(f"/api/targets/{target_id}/result").status_code == 404


def test_analyze_unknown_target_404(client):
    assert client.post("/api/targets/999/analyze").status_code == 404


def test_negative_top_n_does_not_return_garbage(client, target_id):
    """A negative top_n is clamped to 0 rather than becoming a negative slice
    (which would silently return 'all but the last N' frequent areas/contacts)."""
    r = client.post(f"/api/targets/{target_id}/analyze?top_n=-2")
    assert r.status_code == 200
    data = r.get_json()["data"]
    assert data["frequent_areas"] == []
    assert data["frequent_contacts"] == []
    # Home/work detection is independent of top_n and still works.
    assert data["home"]["area"] == "Hamra"
