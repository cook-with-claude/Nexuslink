import io
import pytest
import pandas as pd
from app import create_app


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


def test_valid_import_reports_counts(client, sample_xlsx):
    r = _upload(client, sample_xlsx)
    assert r.status_code == 201
    data = r.get_json()["data"]
    assert data["imported"] > 0
    assert data["skipped"] == 0
    # Phase 1 sample has 5 users; phone-numbers endpoint should list them.
    ds_id = data["dataset_id"]
    pn = client.get(f"/api/datasets/{ds_id}/phone-numbers").get_json()["data"]
    assert len(pn) == 5


def test_missing_column_rejected(client, tmp_path):
    bad = tmp_path / "bad.xlsx"
    pd.DataFrame({"phone_number": ["x"], "area": ["Hamra"]}).to_excel(bad, index=False)
    r = _upload(client, bad)
    assert r.status_code == 400
    assert r.get_json()["error"]["code"] == "SCHEMA_MISMATCH"


def test_bad_rows_are_skipped_with_reasons(client, sample_xlsx, tmp_path):
    df = pd.read_excel(sample_xlsx, dtype={"phone_number": str})
    df.loc[0, "call_type"] = 7          # invalid
    df.loc[1, "timestamp"] = "nope"     # unparseable
    df.loc[2, "duration_seconds"] = -5  # negative
    mixed = tmp_path / "mixed.xlsx"
    df.to_excel(mixed, index=False)
    r = _upload(client, mixed)
    data = r.get_json()["data"]
    assert data["skipped"] >= 3
    assert len(data["skipped_reasons"]) >= 3


def test_corrupt_file_does_not_crash(client, tmp_path):
    junk = tmp_path / "junk.xlsx"
    junk.write_bytes(b"this is not a real xlsx")
    r = _upload(client, junk)
    assert r.status_code == 400
    assert r.get_json()["error"]["code"] == "BAD_FILE"


def test_delete_dataset_cascades(client, sample_xlsx):
    ds_id = _upload(client, sample_xlsx).get_json()["data"]["dataset_id"]
    assert client.delete(f"/api/datasets/{ds_id}").status_code == 200
    assert client.get("/api/datasets").get_json()["data"] == []
    assert client.get(f"/api/datasets/{ds_id}/phone-numbers").status_code == 404
