"""Pattern-detection algorithms for CDR data.

Pure functions only -- no file or network I/O. Each detector receives a
DataFrame already filtered to a single phone_number and returns a
DetectionResult.

Confidence uses a three-gate, weakest-link model. Three independent gates are
scored, and the final confidence is the LOWEST of the three -- a strong gate
never rescues a weak one:

  Gate N         -- how many calls back the result (sample size)
  Gate Share     -- the winner's share of all calls in the window (dominance)
  Gate Closeness -- runner-up / winner (inverted: near-tie = low confidence)

The winner itself is always the area with the most calls; the gates only decide
how much to trust it. When the runner-up is close enough to make it a near-tie,
the result is tagged and the close areas are listed as `alternatives`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import pandas as pd

# Time windows (inclusive lower bound, exclusive upper bound on the hour).
HOME_WINDOW = range(0, 6)  # 00:00-05:59, any day
WORK_WINDOW = range(9, 18)  # 09:00-17:59, Mon-Fri only (weekday() < 5)

# --- Three-gate confidence thresholds ---
# Gate N (sample size). NOTE: these are scaled to the CURRENT synthetic fixtures
# (~20 calls per window). They are placeholders. When dev_fixtures.py is scaled
# up to realistic call volumes, raise N_HIGH toward ~50. See HANDOFF.md.
N_HIGH = 15
N_MEDIUM = 5

# Gate Share (winner's share of all calls in the window).
SHARE_HIGH = 0.40
SHARE_MEDIUM = 0.10

# Gate Closeness (runner-up / winner). Inverted: small ratio = far apart =
# confident. A ratio above NEAR_TIE means it is effectively a coin-flip; that
# same cutoff decides which other areas are listed as `alternatives`.
CLOSENESS_HIGH = 0.30
CLOSENESS_NEAR_TIE = 0.70

# Kept for backwards reference; the volume floor is now expressed via N_MEDIUM.
MIN_RECORDS_FOR_CONFIDENCE = N_MEDIUM

# Ordering used for "max confidence" ceiling checks during validation, and for
# the weakest-link min() across gates.
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
    near_tie: bool = False
    alternatives: List[str] = field(default_factory=list)
    supporting_records: int = 0
    total_window_records: int = 0
    share: Optional[float] = None
    closeness: Optional[float] = None
    gates: Optional[dict] = None  # {"N": .., "share": .., "closeness": ..}

    @property
    def confidence_label(self) -> str:
        """Human-facing label, e.g. 'Low: near tie'."""
        return f"{self.confidence}: near tie" if self.near_tie else self.confidence


def _sorted_areas(window_df: pd.DataFrame) -> List[Tuple[str, int]]:
    """Return (area, count) pairs, most frequent first.

    Deterministic tie-break: count desc, then earliest timestamp asc, then area
    name asc -- so the result never depends on pandas' internal row ordering.
    """
    grouped = window_df.groupby("area")["timestamp"].agg(["count", "min"])
    grouped = grouped.sort_values(
        by=["count", "min", "area"],
        ascending=[False, True, True],
    )
    return [(str(area), int(row["count"])) for area, row in grouped.iterrows()]


def _gate_n(total: int) -> str:
    if total >= N_HIGH:
        return "High"
    if total >= N_MEDIUM:
        return "Medium"
    return "Low"


def _gate_share(top: int, total: int) -> str:
    share = top / total
    if share >= SHARE_HIGH:
        return "High"
    if share >= SHARE_MEDIUM:
        return "Medium"
    return "Low"


def _gate_closeness(closeness: float) -> str:
    if closeness <= CLOSENESS_HIGH:
        return "High"
    if closeness <= CLOSENESS_NEAR_TIE:
        return "Medium"
    return "Low"


def _detect_window(window_df: pd.DataFrame) -> DetectionResult:
    """Shared three-gate logic for window-based detectors (home/work/frequent)."""
    total = len(window_df)
    if total == 0:
        return DetectionResult(
            area=None,
            confidence="Insufficient data",
            total_window_records=0,
        )

    areas = _sorted_areas(window_df)
    top_area, top_count = areas[0]
    second_count = areas[1][1] if len(areas) > 1 else 0

    share = top_count / total
    closeness = second_count / top_count  # top_count > 0 here

    gate_n = _gate_n(total)
    gate_share = _gate_share(top_count, total)
    gate_closeness = _gate_closeness(closeness)
    confidence = min(
        [gate_n, gate_share, gate_closeness],
        key=lambda c: CONFIDENCE_ORDER[c],
    )

    # An area is an "alternative" (and triggers the near-tie tag) when it sits
    # above the closeness cutoff relative to the winner.
    threshold = CLOSENESS_NEAR_TIE * top_count
    alternatives = [area for area, count in areas[1:] if count > threshold]
    near_tie = bool(alternatives)

    return DetectionResult(
        area=top_area,
        confidence=confidence,
        near_tie=near_tie,
        alternatives=alternatives,
        supporting_records=top_count,
        total_window_records=total,
        share=share,
        closeness=closeness,
        gates={"N": gate_n, "share": gate_share, "closeness": gate_closeness},
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

    No time filtering. Same deterministic tie-break as _sorted_areas.
    """
    total = len(df)
    if total == 0:
        return []
    result: List[Tuple[str, int, float]] = []
    for area, count in _sorted_areas(df)[:top_n]:
        result.append((area, count, count / total))
    return result


def detect_frequent_confidence(df: pd.DataFrame) -> DetectionResult:
    """Confidence for the most-frequent area overall (no time filter).

    Frequent areas are about habits, not a single inferred location, so the
    closeness / near-tie machinery does not apply -- confidence here is based on
    the Share gate alone (the lead area's share of all the user's calls).
    """
    total = len(df)
    if total == 0:
        return DetectionResult(area=None, confidence="Insufficient data", total_window_records=0)
    top_area, top_count = _sorted_areas(df)[0]
    share = top_count / total
    confidence = _gate_share(top_count, total)
    return DetectionResult(
        area=top_area,
        confidence=confidence,
        supporting_records=top_count,
        total_window_records=total,
        share=share,
        gates={"share": confidence},
    )
