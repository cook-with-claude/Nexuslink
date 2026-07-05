import io

import pytest
from sqlcipher3 import dbapi2 as sqlcipher

from app import create_app


@pytest.fixture()
def client(app_data_dir, bootstrap_key):
    app = create_app()
    app.config.update(TESTING=True, DB_KEY=bootstrap_key)
    c = app.test_client()
    c.post("/api/setup", json={"username": "nadim", "password": "hunter2"})
    return c


@pytest.fixture()
def dataset_id(client, sample_xlsx):
    with open(sample_xlsx, "rb") as fh:
        data = {"name": "d", "file": (io.BytesIO(fh.read()), "sample.xlsx")}
    return client.post("/api/imports", data=data,
                       content_type="multipart/form-data").get_json()["data"]["dataset_id"]


def test_create_list_delete_target(client, dataset_id):
    r = client.post("/api/targets", json={"name": "subject A",
                    "dataset_id": dataset_id, "phone_number": "01000001"})
    assert r.status_code == 201
    tid = r.get_json()["data"]["id"]
    assert len(client.get("/api/targets").get_json()["data"]) == 1
    assert client.delete(f"/api/targets/{tid}").status_code == 200
    assert client.get("/api/targets").get_json()["data"] == []


def test_duplicate_pair_conflicts_even_with_new_name(client, dataset_id):
    client.post("/api/targets", json={"name": "first",
                "dataset_id": dataset_id, "phone_number": "01000001"})
    r = client.post("/api/targets", json={"name": "different label",
                    "dataset_id": dataset_id, "phone_number": "01000001"})
    assert r.status_code == 409


def test_duplicate_insert_race_returns_conflict(client, dataset_id, monkeypatch):
    from app.targets import routes as targets

    real_get_db = targets.get_db

    class RacingDb:
        def __init__(self, db):
            self._db = db

        def execute(self, sql, params=()):
            if sql.startswith("INSERT INTO targets"):
                raise sqlcipher.IntegrityError(
                    "UNIQUE constraint failed: targets.dataset_id, targets.phone_number"
                )
            return self._db.execute(sql, params)

        def rollback(self):
            return self._db.rollback()

    monkeypatch.setattr(targets, "get_db", lambda: RacingDb(real_get_db()))

    r = client.post("/api/targets", json={"name": "race",
                    "dataset_id": dataset_id, "phone_number": "01000001"})

    assert r.status_code == 409


def test_missing_dataset_or_number_is_404(client, dataset_id):
    assert client.post("/api/targets", json={"name": "x", "dataset_id": 999,
                       "phone_number": "01000001"}).status_code == 404
    assert client.post("/api/targets", json={"name": "x", "dataset_id": dataset_id,
                       "phone_number": "09999999"}).status_code == 404


def test_delete_unknown_target_404(client):
    assert client.delete("/api/targets/9999").status_code == 404
