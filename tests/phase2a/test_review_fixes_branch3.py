"""Regression tests for the 10 code-review fixes landed on `branch-3`.

Khaled's review-fix commit (`ae948b3`) noted the existing suite did not exercise
the bad inputs the fixes address. Each test below pins one fix red->green: revert
the corresponding change and the matching test fails.

Fix numbers refer to the HANDOFF entry "2026-06-27 - Claude: code-review pass".
Fixes #8 (Windows upload-handle close) and #10 (main.py socket close) are not
covered here: both are resource-cleanup paths behind `# pragma: no cover` /
platform-specific GC behavior with no deterministic, non-flaky assertion.
"""

import pytest

from app import account, create_app, validation, detection_bridge
from app.infra import config, storage


@pytest.fixture()
def client(app_data_dir):
    app = create_app()
    app.config.update(TESTING=True)
    c = app.test_client()
    c.post("/api/setup", json={"username": "nadim", "password": "hunter2"})
    return c


# ---------------------------------------------------------------------------
# Fix #1 - account.create_account builds the DB before writing auth.json, and
# cleans up on init failure so /setup stays retryable.
# ---------------------------------------------------------------------------

def test_create_account_init_failure_is_retryable(app_data_dir, monkeypatch):
    def boom(conn):
        raise RuntimeError("simulated schema init failure")

    real_init = storage.init_schema
    monkeypatch.setattr(storage, "init_schema", boom)
    with pytest.raises(RuntimeError, match="simulated schema init failure"):
        account.create_account("nadim", "hunter2")

    # auth.json was never written and the half-built DB was removed -> no stranded
    # "openable" account, and setup can be retried cleanly.
    assert account.account_exists() is False
    assert not config.db_path().exists()

    # Restore ONLY init_schema (monkeypatch.undo() would also drop the fixture's
    # APP_DATA_DIR isolation and leak to the real app-data dir).
    monkeypatch.setattr(storage, "init_schema", real_init)
    key = account.create_account("nadim", "hunter2")
    assert account.account_exists() is True
    conn = storage.connect(key)
    names = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    conn.close()
    assert "datasets" in names


# ---------------------------------------------------------------------------
# Fix #2 - storage.connect sets a busy_timeout so a second concurrent writer
# waits instead of instantly raising "database is locked".
# ---------------------------------------------------------------------------

def test_connection_sets_busy_timeout(app_data_dir):
    key = account.create_account("nadim", "hunter2")
    conn = storage.connect(key)
    (timeout,) = conn.execute("PRAGMA busy_timeout").fetchone()
    conn.close()
    assert timeout == 5000


# ---------------------------------------------------------------------------
# Fix #3 - a non-object JSON body (array/scalar) returns 400, not 500.
# ---------------------------------------------------------------------------

def test_setup_non_object_body_is_400(app_data_dir):
    c = create_app().test_client()
    assert c.post("/api/setup", json=[1, 2, 3]).status_code == 400


def test_login_non_object_body_is_400(client):
    client.post("/api/logout")
    assert client.post("/api/login", json="just-a-string").status_code == 400


def test_change_password_non_object_body_is_400(client):
    assert client.post("/api/change-password", json=[1, 2]).status_code == 400


def test_create_target_non_object_body_is_400(client):
    assert client.post("/api/targets", json=[1, 2]).status_code == 400


# ---------------------------------------------------------------------------
# Fix #4 - non-string username/password/name return a clean 400 (and never
# reach the auth path that would otherwise lock the account out).
# ---------------------------------------------------------------------------

def test_setup_non_string_username_is_400(app_data_dir):
    c = create_app().test_client()
    r = c.post("/api/setup", json={"username": 123, "password": "hunter2"})
    assert r.status_code == 400
    # Nothing was created -> a valid setup still succeeds afterward.
    assert c.post("/api/setup", json={"username": "nadim", "password": "hunter2"}).status_code == 201


def test_login_non_string_password_is_400(client):
    client.post("/api/logout")
    r = client.post("/api/login", json={"username": "nadim", "password": {"x": 1}})
    assert r.status_code == 400
    # The real account is untouched and still logs in.
    assert client.post("/api/login", json={"username": "nadim", "password": "hunter2"}).status_code == 200


def test_create_target_non_string_name_is_400(client):
    r = client.post("/api/targets", json={"name": 5, "dataset_id": 1, "phone_number": "01000001"})
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Codex follow-up - dataset_id / phone_number are bound straight into SQL, so a
# JSON object/array must be rejected with 400 (not raise InterfaceError -> 500).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("dataset_id", [{"x": 1}, [1, 2], "1", 1.0, True])
def test_create_target_non_int_dataset_id_is_400(client, dataset_id):
    r = client.post("/api/targets",
                    json={"name": "t", "dataset_id": dataset_id, "phone_number": "01000001"})
    assert r.status_code == 400
    assert r.get_json()["error"]["code"] == "BAD_REQUEST"


@pytest.mark.parametrize("phone_number", [{"x": 1}, [1, 2], 1000001, ""])
def test_create_target_non_string_phone_number_is_400(client, phone_number):
    r = client.post("/api/targets",
                    json={"name": "t", "dataset_id": 1, "phone_number": phone_number})
    assert r.status_code == 400
    assert r.get_json()["error"]["code"] == "BAD_REQUEST"


def test_create_target_valid_request_still_succeeds(client, sample_xlsx):
    """The tightened type guard must not block a well-formed create (201)."""
    import io

    with open(sample_xlsx, "rb") as fh:
        data = {"name": "ds", "file": (io.BytesIO(fh.read()), "sample.xlsx")}
    up = client.post("/api/imports", data=data, content_type="multipart/form-data").get_json()
    ds_id = up["data"]["dataset_id"]
    phone = client.get(f"/api/datasets/{ds_id}/phone-numbers").get_json()["data"][0]["phone_number"]

    r = client.post("/api/targets",
                    json={"name": "Suspect A", "dataset_id": ds_id, "phone_number": phone})
    assert r.status_code == 201
    assert r.get_json()["data"]["dataset_id"] == ds_id


# ---------------------------------------------------------------------------
# Fix #5 - a timezone-aware timestamp is rejected at import (naive-local
# contract) instead of poisoning a later analysis.
# ---------------------------------------------------------------------------

def test_tz_aware_timestamp_rejected():
    row = {"phone_number": "x", "area": "Hamra", "timestamp": "2024-01-01T03:15:00+02:00",
           "call_type": "1", "duration_seconds": "5"}
    clean, reason = validation.validate_row(row)
    assert clean is None and "timezone" in reason


def test_naive_timestamp_still_accepted():
    row = {"phone_number": "x", "area": "Hamra", "timestamp": "2024-01-01T03:15:00",
           "call_type": "1", "duration_seconds": "5"}
    clean, reason = validation.validate_row(row)
    assert reason is None


# ---------------------------------------------------------------------------
# Fix #6 - a duration above SQLite's signed-64-bit max is skipped (one row)
# instead of OverflowError-ing the entire bulk import.
# ---------------------------------------------------------------------------

def test_overlong_duration_skipped():
    row = {"phone_number": "x", "area": "Hamra", "timestamp": "2024-01-01 03:00:00",
           "call_type": "1", "duration_seconds": str(9_223_372_036_854_775_808)}
    clean, reason = validation.validate_row(row)
    assert clean is None and "out of range" in reason


def test_max_int64_duration_accepted_exactly():
    # The exact int64 max is in range and must be accepted with its precise value.
    # _parse_integer now parses string integers via int() (exact), so the guard's
    # cutoff is the true int64 max -- not the float-rounded approximation that the
    # old float()-first path produced (which mis-rejected this very value).
    max_int64 = 9_223_372_036_854_775_807
    row = {"phone_number": "x", "area": "Hamra", "timestamp": "2024-01-01 03:00:00",
           "call_type": "1", "duration_seconds": str(max_int64)}
    clean, reason = validation.validate_row(row)
    assert reason is None
    assert clean["duration_seconds"] == max_int64  # exact, no float rounding


def test_large_fractional_string_still_falls_through_to_float_path():
    # A non-integer string isn't parsable by int(); it must still be caught as
    # fractional (the float fallback), not silently accepted.
    row = {"phone_number": "x", "area": "Hamra", "timestamp": "2024-01-01 03:00:00",
           "call_type": "1", "duration_seconds": "100.5"}
    clean, reason = validation.validate_row(row)
    assert clean is None and "duration" in reason


# ---------------------------------------------------------------------------
# Fix #7 - delete_dataset writes a DATASET_DELETE audit row like every other
# state-changing endpoint.
# ---------------------------------------------------------------------------

def test_delete_dataset_writes_audit_row(client, sample_xlsx):
    import io

    with open(sample_xlsx, "rb") as fh:
        data = {"name": "ds1", "file": (io.BytesIO(fh.read()), "sample.xlsx")}
    ds_id = client.post("/api/imports", data=data,
                        content_type="multipart/form-data").get_json()["data"]["dataset_id"]
    assert client.delete(f"/api/datasets/{ds_id}").status_code == 200

    key = account.authenticate("nadim", "hunter2")
    conn = storage.connect(key)
    rows = conn.execute(
        "SELECT event_type, detail FROM audit_log WHERE event_type = 'DATASET_DELETE'").fetchall()
    conn.close()
    assert len(rows) == 1
    assert str(ds_id) in rows[0]["detail"]


# ---------------------------------------------------------------------------
# Fix #9 - rows_to_frame drops NaT-timestamp rows, mirroring the frozen loader,
# so a tampered/hand-edited DB can't feed NaT into the detectors.
# ---------------------------------------------------------------------------

def test_bridge_drops_unparseable_timestamp_rows():
    rows = [
        {"phone_number": "01000001", "imei": "350", "area": "Hamra",
         "timestamp": "2024-01-01T03:00:00", "call_type": "1",
         "duration_seconds": "5", "other_party": "0320", "other_imei": "350",
         "other_area": "Hamra"},
        {"phone_number": "01000001", "imei": "350", "area": "Hamra",
         "timestamp": "not-a-real-timestamp", "call_type": "1",
         "duration_seconds": "5", "other_party": "0320", "other_imei": "350",
         "other_area": "Hamra"},
    ]
    frame = detection_bridge.rows_to_frame(rows)
    assert len(frame) == 1
    assert frame["timestamp"].notna().all()
