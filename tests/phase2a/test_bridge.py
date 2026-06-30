import sys
import pathlib
import pandas as pd
import pytest

HERE = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE / "phase1_cdr"))

from app import detection_bridge  # noqa: E402
import detection  # noqa: E402  (Phase 1, read-only)


@pytest.fixture()
def user_a_rows():
    csv = HERE / "phase1_cdr" / "sample_data.csv"
    df = pd.read_csv(csv, dtype={"phone_number": str, "imei": str,
                                 "other_party": str, "other_imei": str})
    a = df[df["phone_number"] == "01000001"]
    return a.to_dict(orient="records")


def test_bridge_matches_direct_phase1_call(user_a_rows):
    frame = detection_bridge.rows_to_frame(user_a_rows)
    bridge = detection_bridge.analyze_frame(frame)

    direct_home = detection.detect_home(frame)
    assert bridge["home"]["area"] == direct_home.area
    assert bridge["home"]["confidence"] == direct_home.confidence
    assert bridge["home"]["gates"] == direct_home.gates

    assert bridge["work"]["area"] == detection.detect_work(frame).area

    direct_contacts = detection.detect_frequent_contacts(frame)
    assert [c["number"] for c in bridge["frequent_contacts"]] == [c.number for c in direct_contacts]


def test_frequent_areas_shape(user_a_rows):
    frame = detection_bridge.rows_to_frame(user_a_rows)
    out = detection_bridge.analyze_frame(frame)
    assert out["frequent_areas"]
    assert {"area", "count", "share"} <= set(out["frequent_areas"][0].keys())
