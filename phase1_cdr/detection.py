"""Pattern-detection algorithms for CDR data.

Pure functions only -- no file or network I/O. Each detector receives a
DataFrame already filtered to a single phone_number and returns a
DetectionResult (or a list, for frequent areas).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import pandas as pd

# Time windows (inclusive lower bound, exclusive upper bound on the hour).
HOME_WINDOW = range(0, 6)  # 00:00-05:59, any day
WORK_WINDOW = range(9, 18)  # 09:00-17:59, Mon-Fri only (weekday() < 5)

MIN_RECORDS_FOR_CONFIDENCE = 5
HIGH_CONFIDENCE_RATIO = 0.60
MEDIUM_CONFIDENCE_RATIO = 0.35

# Ordering used for "max confidence" ceiling checks during validation.
CONFIDENCE_ORDER = {
    "Insufficient data": 0,
    "Low": 1,
    "Medium": 2,
    "High": 3,
}


@dataclass
class DetectionResult:
    area: Optional[str]
    confidence: str
    supporting_records: int
    total_window_records: int
    ratio: Optional[float]


def _pick_top_area(window_df: pd.DataFrame) -> Tuple[str, int]:
    """Return (area, count) for the most frequent area in window_df.

    Tie-break: when two or more areas share the top count, the area whose
    earliest record occurs first chronologically wins. Area name is used as a
    final tiebreaker so the result is fully deterministic and independent of
    pandas' internal row ordering.
    """
    grouped = window_df.groupby("area")["timestamp"].agg(["count", "min"])
    # Sort by count desc, then earliest timestamp asc, then area name asc.
    grouped = grouped.sort_values(
        by=["count", "min", "area"],
        ascending=[False, True, True],
    )
    top_area = grouped.index[0]
    top_count = int(grouped.iloc[0]["count"])
    return top_area, top_count


def _classify(supporting: int, total: int) -> str:
    """Map supporting/total records to a confidence label.

    Checked strictly in this order:
      1. no records in window      -> "Insufficient data"
      2. fewer than 5 records      -> "Low" (volume cap, even if unanimous)
      3. ratio >= 0.60             -> "High"
      4. ratio >= 0.35             -> "Medium"
      5. otherwise                 -> "Low"
    """
    if total == 0:
        return "Insufficient data"
    if total < MIN_RECORDS_FOR_CONFIDENCE:
        return "Low"
    ratio = supporting / total
    if ratio >= HIGH_CONFIDENCE_RATIO:
        return "High"
    if ratio >= MEDIUM_CONFIDENCE_RATIO:
        return "Medium"
    return "Low"


def _detect_window(window_df: pd.DataFrame) -> DetectionResult:
    """Shared logic for window-based detectors (home/work)."""
    total = len(window_df)
    if total == 0:
        return DetectionResult(
            area=None,
            confidence="Insufficient data",
            supporting_records=0,
            total_window_records=0,
            ratio=None,
        )
    area, supporting = _pick_top_area(window_df)
    ratio = supporting / total
    return DetectionResult(
        area=area,
        confidence=_classify(supporting, total),
        supporting_records=supporting,
        total_window_records=total,
        ratio=ratio,
    )


def detect_home(df: pd.DataFrame) -> DetectionResult:
    """Detect the likely home area using overnight records (hour in [0, 6))."""
    window = df[df["timestamp"].dt.hour.isin(HOME_WINDOW)]
    return _detect_window(window)


def detect_work(df: pd.DataFrame) -> DetectionResult:
    """Detect the likely work area using weekday daytime records.

    Window: hour in [9, 18) and weekday() < 5 (Mon-Fri).
    """
    hours = df["timestamp"].dt.hour
    weekdays = df["timestamp"].dt.weekday
    window = df[hours.isin(WORK_WINDOW) & (weekdays < 5)]
    return _detect_window(window)


def detect_frequent_areas(
    df: pd.DataFrame, top_n: int = 3
) -> List[Tuple[str, int, float]]:
    """Return the top_n areas across all records as (area, count, share).

    No time filtering. Same deterministic tie-break as _pick_top_area: count
    desc, then earliest timestamp asc, then area name asc.
    """
    total = len(df)
    if total == 0:
        return []
    grouped = df.groupby("area")["timestamp"].agg(["count", "min"])
    grouped = grouped.sort_values(
        by=["count", "min", "area"],
        ascending=[False, True, True],
    )
    result: List[Tuple[str, int, float]] = []
    for area, row in grouped.head(top_n).iterrows():
        count = int(row["count"])
        result.append((area, count, count / total))
    return result
