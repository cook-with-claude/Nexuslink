"""Characterization tests for the route-owned transaction contract (ADR 0001, Step 5).

These pin the *current* mutate -> audit -> commit / rollback behavior BEFORE the
repo extractions (Steps 6-8) move the SQL out of the routes. They pass on today's
code and must stay green through the extractions: the route owns the unit-of-work,
so if the audit write fails, nothing the request mutated may be committed; and a
duplicate-target 409 must leave the connection clean.

Failures are injected by monkeypatching `app.audit.log.write_audit` (the routes
hold a reference to that same module object, so the patched function is what they
call). The client fixtures use TESTING=True, so a route exception propagates to the
caller instead of becoming a 500 -- but the app-context teardown still runs and
rolls back the uncommitted transaction, which is exactly what these assert.
"""

import io

import pytest

from app import create_app
from app.audit import log as audit_log


@pytest.fixture()
def client(app_data_dir):
    app = create_app()
    app.config.update(TESTING=True)
    c = app.test_client()
    c.post("/api/setup", json={"username": "nadim", "password": "hunter2"})
    return c


def _upload(client, path, name="dataset1"):
    with open(path, "rb") as fh:
        data = {"name": name, "file": (io.BytesIO(fh.read()), "sample.xlsx")}
    return client.post("/api/imports", data=data, content_type="multipart/form-data")


def _boom(*args, **kwargs):
    raise RuntimeError("injected audit failure")


def test_audit_failure_during_import_persists_nothing(client, sample_xlsx, monkeypatch):
    monkeypatch.setattr(audit_log, "write_audit", _boom)
    with pytest.raises(RuntimeError):
        _upload(client, sample_xlsx)
    # A fresh request opens a new connection: the rolled-back import left no dataset.
    assert client.get("/api/datasets").get_json()["data"] == []


def test_audit_failure_during_delete_does_not_commit(client, sample_xlsx, monkeypatch):
    ds_id = _upload(client, sample_xlsx).get_json()["data"]["dataset_id"]
    monkeypatch.setattr(audit_log, "write_audit", _boom)
    with pytest.raises(RuntimeError):
        client.delete(f"/api/datasets/{ds_id}")
    # The delete's audit write failed before commit -> the dataset is still there.
    datasets = client.get("/api/datasets").get_json()["data"]
    assert any(d["id"] == ds_id for d in datasets)


def test_audit_failure_during_analysis_persists_no_result(client, sample_xlsx, monkeypatch):
    ds_id = _upload(client, sample_xlsx).get_json()["data"]["dataset_id"]
    phones = client.get(f"/api/datasets/{ds_id}/phone-numbers").get_json()["data"]
    tid = client.post("/api/targets", json={"name": "A", "dataset_id": ds_id,
                      "phone_number": phones[0]["phone_number"]}).get_json()["data"]["id"]
    monkeypatch.setattr(audit_log, "write_audit", _boom)
    with pytest.raises(RuntimeError):
        client.post(f"/api/targets/{tid}/analyze")
    # The analysis_results INSERT was rolled back with the failed audit write.
    assert client.get(f"/api/targets/{tid}/result").status_code == 404


def test_duplicate_target_409_leaves_unit_of_work_clean(client, sample_xlsx):
    ds_id = _upload(client, sample_xlsx).get_json()["data"]["dataset_id"]
    phones = [p["phone_number"] for p in
              client.get(f"/api/datasets/{ds_id}/phone-numbers").get_json()["data"]]
    first = client.post("/api/targets", json={"name": "first", "dataset_id": ds_id,
                        "phone_number": phones[0]})
    assert first.status_code == 201
    dup = client.post("/api/targets", json={"name": "second", "dataset_id": ds_id,
                      "phone_number": phones[0]})
    assert dup.status_code == 409
    # The 409 path must leave the connection in a clean state: a different target
    # still inserts successfully.
    other = client.post("/api/targets", json={"name": "third", "dataset_id": ds_id,
                        "phone_number": phones[1]})
    assert other.status_code == 201
