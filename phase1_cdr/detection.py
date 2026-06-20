"""Pattern-detection algorithms for CDR data.

Pure functions only -- no file or network I/O. Each detector receives a
DataFrame already filtered to a single phone_number and returns a
DetectionResult.

Confidence uses a four-gate, weakest-link model. Four independent gates are
scored, and the final confidence is the LOWEST of the four -- a strong gate
never rescues a weak one:

  Gate N         -- how many calls back the result (absolute sample size)
  Gate Share     -- the winner's share of all calls in the window (dominance)
  Gate Closeness -- runner-up / winner (inverted: near-tie = low confidence)
  Gate Density   -- distinct active days in the window / total days observed
                    (RELATIVE coverage: a handful of records over a week is
                    decent; the same handful over three years is not)

N is an absolute floor; Density is the same volume question made relative to how
long we have been watching the user. The two are complementary -- N stops a tiny
sample from ever scoring High (even at 100% coverage), while Density stops a
sample that is sparse relative to a long observation span.

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

# Gate Density (RELATIVE volume): distinct active days in the window divided by
# the total span of days we have observed this user (first record to last).
# Distinct *days*, not raw record count -- one chatty night should not look like
# many nights of evidence, and raw volume is already the N gate's job.
# NOTE: like the N thresholds these are calibrated to the current ~28-day
# fixtures (User A covers ~0.52) and are placeholders. Revisit when
# dev_fixtures.py scales up to realistic, longer-span volumes. See HANDOFF.md.
DENSITY_HIGH = 0.45
DENSITY_MEDIUM = 0.20

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
    density: Optional[float] = None  # active days in window / days observed
    gates: Optional[dict] = None  # {"N": .., "share": .., "closeness": .., "density": ..}

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


def _gate_density(coverage: float) -> str:
    if coverage >= DENSITY_HIGH:
        return "High"
    if coverage >= DENSITY_MEDIUM:
        return "Medium"
    return "Low"


def _observed_days(df: pd.DataFrame) -> int:
    """Span (in whole days) from the user's first record to their last, inclusive.

    Uses the FULL user frame -- the question the density gate answers is "how
    long have we been observing this person", which is independent of any single
    window. A single-day span counts as 1 (never zero), so the gate never
    divides by zero.
    """
    if len(df) == 0:
        return 0
    span = df["timestamp"].max() - df["timestamp"].min()
    return int(span.days) + 1


def _detect_window(window_df: pd.DataFrame, observed_days: int) -> DetectionResult:
    """Shared four-gate logic for window-based detectors (home/work).

    `observed_days` is the user's full observation span (see _observed_days) and
    powers the Density gate; it is independent of the window filter.
    """
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

    # Distinct calendar days touched in this window, relative to the full span we
    # have been observing the user. window_df is non-empty here, so it is a
    # subset of a non-empty frame and observed_days >= 1.
    active_days = int(window_df["timestamp"].dt.normalize().nunique())
    coverage = active_days / observed_days if observed_days else 0.0

    gate_n = _gate_n(total)
    gate_share = _gate_share(top_count, total)
    gate_closeness = _gate_closeness(closeness)
    gate_density = _gate_density(coverage)
    confidence = min(
        [gate_n, gate_share, gate_closeness, gate_density],
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
        density=coverage,
        gates={
            "N": gate_n,
            "share": gate_share,
            "closeness": gate_closeness,
            "density": gate_density,
        },
    )


def detect_home(df: pd.DataFrame) -> DetectionResult:
    """Detect the likely home area using overnight records (hour in [0, 6))."""
    window = df[df["timestamp"].dt.hour.isin(HOME_WINDOW)]
    return _detect_window(window, _observed_days(df))


def detect_work(df: pd.DataFrame) -> DetectionResult:
    """Detect the likely work area using weekday daytime records.

    Window: hour in [9, 18) and weekday() < 5 (Mon-Fri).
    """
    hours = df["timestamp"].dt.hour
    weekdays = df["timestamp"].dt.weekday
    window = df[hours.isin(WORK_WINDOW) & (weekdays < 5)]
    return _detect_window(window, _observed_days(df))


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
