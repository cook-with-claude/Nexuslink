"""Unit tests for the pure four-gate detection logic.

These hand-build tiny DataFrames so they exercise detection.py directly and do
NOT depend on the fixture generator.
"""

from __future__ import annotations

import pandas as pd

from detection import (
    detect_frequent_areas,
    detect_frequent_confidence,
    detect_home,
    detect_work,
    _sorted_areas,
)


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


def _home(area, hour, day):
    return (area, f"2024-01-{day:02d} {hour:02d}:00:00")


def test_empty_window_is_insufficient():
    # All records at 12:00 (outside the home window [0, 6)).
    df = _df([("Hamra", "2024-01-01 12:00:00"), ("Hamra", "2024-01-02 12:00:00")])
    result = detect_home(df)
    assert result.confidence == "Insufficient data"
    assert result.area is None
    assert result.total_window_records == 0


def test_n_gate_caps_small_sample_at_low():
    # 4 overnight records, all one area: Share+Closeness+Density say High, but the
    # N gate (4 < N_MEDIUM=15) caps the weakest link at Low.
    df = _df([_home("Hamra", 1, d) for d in range(1, 5)])
    result = detect_home(df)
    assert result.total_window_records == 4
    assert result.area == "Hamra"
    assert result.gates["N"] == "Low"
    assert result.confidence == "Low"


def test_clear_winner_is_high():
    # 60 Hamra (N >= N_HIGH=50) across 28 distinct nights, plus light noise ->
    # N High, Share High, Closeness High, Density High (28 active days / 28-day
    # span) -> overall High.
    rows = [("Hamra", f"2024-01-{(i % 28) + 1:02d} 02:00:00") for i in range(60)]
    rows += [("Achrafieh", f"2024-01-{d:02d} 03:00:00") for d in range(1, 6)]
    rows += [("Verdun", f"2024-01-{d:02d} 04:00:00") for d in range(1, 4)]
    result = detect_home(_df(rows))
    assert result.area == "Hamra"
    assert result.gates["N"] == "High"
    assert result.confidence == "High"
    assert result.near_tie is False
    assert result.alternatives == []


def test_near_tie_is_low_with_alternatives():
    # 6 Hamra vs 5 Achrafieh overnight: closeness 5/6 = 0.83 > 0.70 -> near tie.
    rows = [_home("Hamra", 1, d) for d in range(1, 7)]
    rows += [_home("Achrafieh", 2, d) for d in range(7, 12)]
    result = detect_home(_df(rows))
    assert result.area == "Hamra"
    assert result.confidence == "Low"
    assert result.near_tie is True
    assert result.confidence_label == "Low: near tie"
    assert result.alternatives == ["Achrafieh"]


def test_alternatives_only_lists_areas_above_cutoff():
    # Winner 4 (Downtown), Mazraa 3 and Verdun 3 are >70% of 4 (=2.8); Hamra 2 is not.
    rows = [_home("Downtown", 1, d) for d in range(1, 5)]
    rows += [_home("Mazraa", 2, d) for d in range(5, 8)]
    rows += [_home("Verdun", 3, d) for d in range(8, 11)]
    rows += [_home("Hamra", 4, 11), _home("Hamra", 4, 12)]
    result = detect_home(_df(rows))
    assert result.area == "Downtown"
    assert result.near_tie is True
    assert sorted(result.alternatives) == ["Mazraa", "Verdun"]


def test_share_gate_caps_dominant_but_thin_winner():
    # Winner 20 (N_MEDIUM=15 <= 20 < N_HIGH=50) vs six distinct 1-night areas:
    # Share High, Closeness High (1/20), Density High, but only 20 records ->
    # N gate Medium caps it below High.
    rows = [_home("Hamra", 1, d) for d in range(1, 21)]
    rows += [(f"Area{i}", f"2024-01-{20 + i:02d} 02:00:00") for i in range(1, 7)]
    result = detect_home(_df(rows))
    assert result.area == "Hamra"
    assert result.gates["closeness"] == "High"
    assert result.gates["N"] == "Medium"
    assert result.confidence == "Medium"


def test_tie_breaks_on_earliest_timestamp():
    # Verdun and Hamra both 2 records; Verdun's earliest is earlier -> wins.
    df = _df(
        [
            ("Verdun", "2024-01-01 01:00:00"),
            ("Hamra", "2024-01-01 02:00:00"),
            ("Hamra", "2024-01-02 02:00:00"),
            ("Verdun", "2024-01-03 04:00:00"),
        ]
    )
    areas = _sorted_areas(df)
    assert areas[0] == ("Verdun", 2)


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


def test_frequent_areas_list_and_confidence():
    # No time filter. 4 Hamra, 1 Verdun, 1 Mazraa -> Hamra leads.
    # Frequent confidence is share-only: 4/6 = 0.67 >= 0.40 -> High, and the
    # closeness / near-tie machinery does not apply.
    rows = [("Hamra", f"2024-01-0{d} 12:00:00") for d in range(1, 5)]
    rows += [("Verdun", "2024-01-05 12:00:00"), ("Mazraa", "2024-01-06 12:00:00")]
    df = _df(rows)
    areas = [a for a, _c, _s in detect_frequent_areas(df)]
    assert areas[0] == "Hamra"
    lead = detect_frequent_confidence(df)
    assert lead.area == "Hamra"
    assert lead.confidence == "High"
    assert lead.near_tie is False
    assert lead.closeness is None  # share-only; closeness not computed


def _spaced_nights(area, count, step_days, start="2024-01-01"):
    """`count` overnight records for one area, one per distinct day, `step_days`
    apart -- used to dial in a specific Density coverage."""
    base = pd.Timestamp(start)
    return [
        (area, (base + pd.Timedelta(days=i * step_days)).strftime("%Y-%m-%d 02:00:00"))
        for i in range(count)
    ]


def test_density_gate_caps_long_sparse_span():
    # 20 unanimous Hamra nights (N_MEDIUM=15 <= 20 < N_HIGH=50 -> Medium), one
    # every 11 days across a ~210-day span. Share 100% -> High, Closeness 0 ->
    # High, but 20 active days / 210-day span -> coverage ~0.09 -> Density Low.
    rows = _spaced_nights("Hamra", 20, 11)
    result = detect_home(_df(rows))
    assert result.area == "Hamra"
    assert result.gates["N"] == "Medium"      # absolute count alone allows Medium
    assert result.gates["share"] == "High"
    assert result.gates["closeness"] == "High"
    assert result.gates["density"] == "Low"   # relative coverage is the weak link
    assert result.confidence == "Low"
    assert result.density < 0.15


def test_density_gate_caps_high_to_medium():
    # 60 unanimous Hamra nights (N >= N_HIGH=50 -> High, Share High, Closeness
    # High), one every 3 days so coverage is 60 active days / ~178-day span ~=
    # 0.34 -> Density Medium is the binding gate.
    rows = _spaced_nights("Hamra", 60, 3)
    result = detect_home(_df(rows))
    assert result.area == "Hamra"
    assert result.gates["N"] == "High"        # clears the absolute floor
    assert result.gates["density"] == "Medium"
    assert result.confidence == "Medium"      # density is the binding gate
    assert 0.15 <= result.density < 0.40
