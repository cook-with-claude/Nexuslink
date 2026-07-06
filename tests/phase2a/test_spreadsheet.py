"""Spreadsheet-tab endpoints: the read-only records page and the filtered
frequency explorer (a descriptive tally, deliberately NOT a detection)."""

import io

import pandas as pd
import pytest

from app import create_app

COLUMNS = ["phone_number", "imei", "area", "timestamp", "call_type",
           "duration_seconds", "other_party", "other_imei", "other_area"]

# Six controlled rows for one phone. Tallies the tests assert against:
#   area:        A1 x3, A2 x2, A3 x1
#   call_type:   1 x2, 11 x2, 2 x1, 22 x1
#   other_party: P1 x3, P2 x2, blank x1 (blank -> NULL, excluded from ranking)
#   hours:       09,09,10, 22,23, 02
ROWS = [
    ("500", "i1", "A1", "2026-01-01T09:00:00", 1, 60, "P1", "", ""),
    ("500", "i1", "A1", "2026-01-02T09:30:00", 1, 30, "P1", "", ""),
    ("500", "i1", "A1", "2026-01-03T10:00:00", 11, 0, "P2", "", ""),
    ("500", "i1", "A2", "2026-01-04T22:15:00", 11, 0, "P2", "", ""),
    ("500", "i1", "A2", "2026-01-05T23:45:00", 2, 120, "", "", ""),
    ("500", "i1", "A3", "2026-01-06T02:00:00", 22, 0, "P1", "", ""),
]


@pytest.fixture()
def client(app_data_dir, bootstrap_key):
    app = create_app()
    app.config.update(TESTING=True, DB_KEY=bootstrap_key)
    c = app.test_client()
    c.post("/api/setup", json={"username": "nadim", "password": "hunter2"})
    return c


def _import_fixture(client, tmp_path, rows=ROWS):
    df = pd.DataFrame(rows, columns=COLUMNS)
    path = tmp_path / "slice.xlsx"
    df.to_excel(path, index=False, engine="openpyxl")
    with open(path, "rb") as fh:
        data = {"name": "slice", "file": (io.BytesIO(fh.read()), "slice.xlsx")}
    res = client.post("/api/imports", data=data, content_type="multipart/form-data")
    return res.get_json()["data"]["dataset_id"]


@pytest.fixture()
def dataset_id(client, tmp_path):
    return _import_fixture(client, tmp_path)


@pytest.fixture()
def target_id(client, dataset_id):
    return client.post("/api/targets", json={
        "name": "T", "dataset_id": dataset_id, "phone_number": "500",
    }).get_json()["data"]["id"]


# ---- records page ----

def test_records_requires_auth(app_data_dir, bootstrap_key):
    app = create_app()
    app.config.update(TESTING=True, DB_KEY=bootstrap_key)
    assert app.test_client().get("/api/datasets/1/records").status_code == 401


def test_records_unknown_dataset_404(client):
    assert client.get("/api/datasets/999/records").status_code == 404


def test_records_returns_all_columns_in_import_order(client, dataset_id):
    data = client.get(f"/api/datasets/{dataset_id}/records").get_json()["data"]
    assert data["total"] == 6
    assert len(data["rows"]) == 6
    first = data["rows"][0]
    assert set(first) == {"id", "phone_number", "imei", "area", "timestamp",
                          "call_type", "duration_seconds", "other_party",
                          "other_imei", "other_area"}
    assert first["area"] == "A1"
    assert first["timestamp"] == "2026-01-01T09:00:00"
    assert first["call_type"] == 1          # numeric code, labeled client-side only
    assert data["rows"][4]["other_party"] is None   # blank stored as NULL


def test_records_pages(client, dataset_id):
    page1 = client.get(f"/api/datasets/{dataset_id}/records?offset=0&limit=4").get_json()["data"]
    page2 = client.get(f"/api/datasets/{dataset_id}/records?offset=4&limit=4").get_json()["data"]
    assert [len(page1["rows"]), len(page2["rows"])] == [4, 2]
    assert page1["total"] == page2["total"] == 6
    ids = [r["id"] for r in page1["rows"] + page2["rows"]]
    assert ids == sorted(ids)


def test_records_bad_paging_falls_back_to_defaults(client, dataset_id):
    data = client.get(f"/api/datasets/{dataset_id}/records?offset=x&limit=-9").get_json()["data"]
    assert data["offset"] == 0
    assert data["limit"] == 1               # -9 clamped up to the minimum
    data = client.get(f"/api/datasets/{dataset_id}/records?limit=99999").get_json()["data"]
    assert data["limit"] == 500             # cap


# ---- records user filter ----

# Two subscribers in one dataset: "500" x2, "600" x1.
TWO_USER_ROWS = [
    ("500", "i1", "A1", "2026-01-01T09:00:00", 1, 60, "P1", "", ""),
    ("600", "i2", "B1", "2026-01-01T10:00:00", 2, 30, "P9", "", ""),
    ("500", "i1", "A2", "2026-01-02T11:00:00", 11, 0, "P2", "", ""),
]


@pytest.fixture()
def two_user_dataset_id(client, tmp_path):
    return _import_fixture(client, tmp_path, rows=TWO_USER_ROWS)


def test_records_filters_by_phone_number(client, two_user_dataset_id):
    data = client.get(
        f"/api/datasets/{two_user_dataset_id}/records?phone_number=500").get_json()["data"]
    assert data["phone_number"] == "500"
    assert data["total"] == 2
    assert [r["phone_number"] for r in data["rows"]] == ["500", "500"]


def test_records_phone_number_filter_pages(client, two_user_dataset_id):
    data = client.get(
        f"/api/datasets/{two_user_dataset_id}/records"
        "?phone_number=500&offset=1&limit=1").get_json()["data"]
    assert data["total"] == 2               # total counts the FILTERED set
    assert len(data["rows"]) == 1
    assert data["rows"][0]["area"] == "A2"


def test_records_blank_phone_number_means_all_users(client, two_user_dataset_id):
    data = client.get(
        f"/api/datasets/{two_user_dataset_id}/records?phone_number=").get_json()["data"]
    assert data["phone_number"] is None
    assert data["total"] == 3


def test_records_unknown_phone_number_matches_nothing(client, two_user_dataset_id):
    data = client.get(
        f"/api/datasets/{two_user_dataset_id}/records?phone_number=999").get_json()["data"]
    assert data["total"] == 0
    assert data["rows"] == []


def test_records_call_type_filter(client, two_user_dataset_id):
    data = client.get(
        f"/api/datasets/{two_user_dataset_id}/records?call_type=11").get_json()["data"]
    assert data["total"] == 1
    assert data["rows"][0]["area"] == "A2"


def test_records_malformed_call_type_is_ignored(client, two_user_dataset_id):
    # Consistent with the paging params: a single local client, read-only view.
    data = client.get(
        f"/api/datasets/{two_user_dataset_id}/records?call_type=abc").get_json()["data"]
    assert data["total"] == 3


def test_records_area_filter_is_substring_case_insensitive(client, two_user_dataset_id):
    data = client.get(
        f"/api/datasets/{two_user_dataset_id}/records?area=a").get_json()["data"]
    assert data["total"] == 2               # A1 + A2; "B1" has no 'a'
    assert {r["area"] for r in data["rows"]} == {"A1", "A2"}


def test_records_area_filter_treats_like_wildcards_as_literals(client, two_user_dataset_id):
    assert client.get(
        f"/api/datasets/{two_user_dataset_id}/records?area=%25").get_json()["data"]["total"] == 0
    assert client.get(
        f"/api/datasets/{two_user_dataset_id}/records?area=_").get_json()["data"]["total"] == 0


def test_records_other_party_filter(client, two_user_dataset_id):
    data = client.get(
        f"/api/datasets/{two_user_dataset_id}/records?other_party=9").get_json()["data"]
    assert data["total"] == 1
    assert data["rows"][0]["other_party"] == "P9"


def test_records_filters_compose(client, two_user_dataset_id):
    data = client.get(
        f"/api/datasets/{two_user_dataset_id}/records"
        "?phone_number=500&area=A&call_type=1").get_json()["data"]
    assert data["total"] == 1
    assert data["rows"][0]["area"] == "A1"


# ---- records sorting ----

def test_records_sort_by_timestamp(client, two_user_dataset_id):
    newest = client.get(
        f"/api/datasets/{two_user_dataset_id}/records"
        "?sort=timestamp&dir=desc").get_json()["data"]["rows"]
    stamps = [r["timestamp"] for r in newest]
    assert stamps == sorted(stamps, reverse=True)
    oldest = client.get(
        f"/api/datasets/{two_user_dataset_id}/records?sort=timestamp").get_json()["data"]["rows"]
    assert [r["timestamp"] for r in oldest] == sorted(stamps)


def test_records_sort_by_duration(client, two_user_dataset_id):
    longest = client.get(
        f"/api/datasets/{two_user_dataset_id}/records"
        "?sort=duration_seconds&dir=desc").get_json()["data"]["rows"]
    assert [r["duration_seconds"] for r in longest] == [60, 30, 0]


def test_records_sort_composes_with_filters(client, two_user_dataset_id):
    rows = client.get(
        f"/api/datasets/{two_user_dataset_id}/records"
        "?phone_number=500&sort=duration_seconds&dir=desc").get_json()["data"]["rows"]
    assert [r["duration_seconds"] for r in rows] == [60, 0]


def test_records_unknown_sort_falls_back_to_import_order(client, two_user_dataset_id):
    rows = client.get(
        f"/api/datasets/{two_user_dataset_id}/records"
        "?sort=phone_number; DROP TABLE cdr_records").get_json()["data"]["rows"]
    ids = [r["id"] for r in rows]
    assert ids == sorted(ids)


# ---- frequency explorer ----

def test_frequency_unknown_target_404(client):
    assert client.get("/api/targets/999/frequency").status_code == 404


def test_frequency_rejects_unknown_rank_by(client, target_id):
    res = client.get(f"/api/targets/{target_id}/frequency?rank_by=phone_number")
    assert res.status_code == 400
    assert res.get_json()["error"]["code"] == "BAD_REQUEST"


@pytest.mark.parametrize("query", ["hour_from=24", "hour_to=-1", "call_type=abc",
                                   "date_from=01/05/2026", "date_to=nope"])
def test_frequency_rejects_malformed_filters(client, target_id, query):
    assert client.get(f"/api/targets/{target_id}/frequency?{query}").status_code == 400


def test_frequency_unfiltered_ranks_area(client, target_id):
    data = client.get(f"/api/targets/{target_id}/frequency").get_json()["data"]
    assert data["rank_by"] == "area"
    assert data["total_records"] == 6
    assert data["top"] == [{"value": "A1", "count": 3},
                           {"value": "A2", "count": 2},
                           {"value": "A3", "count": 1}]


def test_frequency_area_filter_is_case_insensitive(client, target_id):
    """The explorer's "exact area" filter matches regardless of capitalization,
    so a value copied from the case-insensitive records grid still counts."""
    data = client.get(
        f"/api/targets/{target_id}/frequency?area=a1").get_json()["data"]
    assert data["total_records"] == 3
    assert data["top"] == [{"value": "A1", "count": 3}]


def test_frequency_is_a_tally_not_a_detection(client, target_id):
    """The explorer's contract: no confidence, no gates, no home/work labels."""
    data = client.get(f"/api/targets/{target_id}/frequency").get_json()["data"]
    assert set(data) == {"target", "rank_by", "total_records", "top"}


def test_frequency_rank_by_partner_excludes_nulls(client, target_id):
    data = client.get(
        f"/api/targets/{target_id}/frequency?rank_by=other_party").get_json()["data"]
    assert data["total_records"] == 6       # the NULL row still counts as a record
    assert data["top"] == [{"value": "P1", "count": 3}, {"value": "P2", "count": 2}]


def test_frequency_filters_compose(client, target_id):
    data = client.get(
        f"/api/targets/{target_id}/frequency?rank_by=area&call_type=11").get_json()["data"]
    assert data["total_records"] == 2
    # tie broken by value ascending
    assert data["top"] == [{"value": "A1", "count": 1}, {"value": "A2", "count": 1}]


def test_frequency_date_range(client, target_id):
    data = client.get(
        f"/api/targets/{target_id}/frequency?date_from=2026-01-04").get_json()["data"]
    assert data["total_records"] == 3
    data = client.get(
        f"/api/targets/{target_id}/frequency?date_to=2026-01-02").get_json()["data"]
    assert data["total_records"] == 2


def test_frequency_hour_window_wraps_midnight(client, target_id):
    data = client.get(
        f"/api/targets/{target_id}/frequency?hour_from=22&hour_to=6").get_json()["data"]
    assert data["total_records"] == 3       # 22:15, 23:45, 02:00
    assert data["top"][0] == {"value": "A2", "count": 2}
    data = client.get(
        f"/api/targets/{target_id}/frequency?hour_from=9&hour_to=10").get_json()["data"]
    assert data["total_records"] == 3


def test_frequency_rank_by_call_type_returns_codes(client, target_id):
    """Codes stay numeric in the API; the UI maps them to labels via the single
    call-types lookup (mirroring the frozen detection.py constants)."""
    data = client.get(
        f"/api/targets/{target_id}/frequency?rank_by=call_type").get_json()["data"]
    assert data["top"][:2] == [{"value": 1, "count": 2}, {"value": 11, "count": 2}]
