"""Unit tests for the pure detection logic.

These hand-build tiny DataFrames so they exercise detection.py directly and do
NOT depend on the fixture generator.
"""

from __future__ import annotations

import pandas as pd

from detection import detect_home, detect_work, _pick_top_area


def _df(rows):
    """rows: list of (area, timestamp_str). Builds a one-user CDR frame."""
    return pd.DataFrame(
        {
            "phone_number": ["01000000"] * len(rows),
            "imei": ["350000000000000"] * len(rows),
            "area": [r[0] for r in rows],
            "timestamp": pd.to_datetime([r[1] for r in rows]),
            "call_type": [1] * len(rows),
            "duration_seconds": [60] * len(rows),
        }
    )


def test_empty_window_is_insufficient():
    # All records are at 12:00 (outside the home window [0, 6)).
    df = _df([("Hamra", "2024-01-01 12:00:00"), ("Hamra", "2024-01-02 12:00:00")])
    result = detect_home(df)
    assert result.confidence == "Insufficient data"
    assert result.area is None
    assert result.total_window_records == 0


def test_four_records_capped_at_low():
    # 4 overnight records, all one area -> 100% ratio but below the volume floor.
    df = _df(
        [
            ("Hamra", "2024-01-01 01:00:00"),
            ("Hamra", "2024-01-02 02:00:00"),
            ("Hamra", "2024-01-03 03:00:00"),
            ("Hamra", "2024-01-04 04:00:00"),
        ]
    )
    result = detect_home(df)
    assert result.total_window_records == 4
    assert result.area == "Hamra"
    assert result.confidence == "Low"  # volume cap overrides the 100% ratio


def test_five_records_ratio_060_is_high():
    # 5 overnight records, 3 Hamra / 2 other = 0.60 exactly -> High (inclusive).
    df = _df(
        [
            ("Hamra", "2024-01-01 01:00:00"),
            ("Hamra", "2024-01-02 02:00:00"),
            ("Hamra", "2024-01-03 03:00:00"),
            ("Verdun", "2024-01-04 04:00:00"),
            ("Verdun", "2024-01-05 05:00:00"),
        ]
    )
    result = detect_home(df)
    assert result.total_window_records == 5
    assert result.area == "Hamra"
    assert result.ratio == 0.60
    assert result.confidence == "High"


def test_ratio_035_is_medium():
    # 20 overnight records, top area 7/20 = 0.35 exactly -> Medium (inclusive).
    # 7 Hamra, 7 Verdun, 6 Mazraa across distinct timestamps.
    # Hamra is the top by tie-break (earliest), 7/20 = 0.35.
    rows = []
    base_days = list(range(1, 21))
    areas = ["Hamra"] * 7 + ["Verdun"] * 7 + ["Mazraa"] * 6
    for day, area in zip(base_days, areas):
        rows.append((area, f"2024-01-{day:02d} 03:00:00"))
    df = _df(rows)
    result = detect_home(df)
    assert result.total_window_records == 20
    assert result.supporting_records == 7
    assert abs(result.ratio - 0.35) < 1e-9
    assert result.confidence == "Medium"


def test_tie_breaks_on_earliest_timestamp():
    # Verdun and Hamra both have 2 records; Verdun's earliest is earlier -> wins.
    df = _df(
        [
            ("Verdun", "2024-01-01 01:00:00"),  # earliest overall
            ("Hamra", "2024-01-01 02:00:00"),
            ("Hamra", "2024-01-02 02:00:00"),
            ("Verdun", "2024-01-03 04:00:00"),
        ]
    )
    area, count = _pick_top_area(df)
    assert area == "Verdun"
    assert count == 2


def test_saturday_excluded_from_work():
    # 2024-01-06 is a Saturday; its 12:00 record must be excluded from work.
    df = _df(
        [
            ("Downtown", "2024-01-06 12:00:00"),  # Saturday, in work hours
            ("Downtown", "2024-01-01 12:00:00"),  # Monday, counts
        ]
    )
    result = detect_work(df)
    assert result.total_window_records == 1
    assert result.area == "Downtown"
