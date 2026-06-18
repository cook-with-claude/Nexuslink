"""Throwaway development fixture generator.

Deterministically builds a synthetic CDR dataset (sample_data.csv) and an
independently-computed ground truth (ground_truth.json) for four test users.

IMPORTANT:
  * All data here is synthetic, produced with a fixed seed. No real telecom
    data and no LLM is ever involved.
  * This file is disposable. The team's real generator will replace it and
    must emit the same 6-column schema.
  * ground_truth.json is computed by a LOCAL tally (plain groupby) below --
    it deliberately does NOT import detection.py, so validating detection.py
    against this file actually proves something.
"""

from __future__ import annotations

import json
import os
import random

import numpy as np
import pandas as pd

SEED = 42
random.seed(SEED)
np.random.seed(SEED)

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(HERE, "sample_data.csv")
GROUND_TRUTH_PATH = os.path.join(HERE, "ground_truth.json")

# 2024-01-01 is a Monday. 28 consecutive days give us 20 weekdays + 8 weekend.
ALL_DATES = [pd.Timestamp("2024-01-01") + pd.Timedelta(days=d) for d in range(28)]
WEEKDAY_DATES = [d for d in ALL_DATES if d.weekday() < 5]

CALL_TYPES = [1, 2, 11, 22]

_records: list[dict] = []


def _add(phone: str, imei: str, n: int, area: str, window: str) -> None:
    """Append n synthetic records for one user/area in a given time window."""
    for _ in range(n):
        if window == "home":  # hour in [0, 6), any day
            date = random.choice(ALL_DATES)
            hour = random.randint(0, 5)
        elif window == "work":  # hour in [9, 18), weekdays only
            date = random.choice(WEEKDAY_DATES)
            hour = random.randint(9, 17)
        elif window == "evening":  # outside both windows
            date = random.choice(ALL_DATES)
            hour = random.randint(19, 23)
        else:
            raise ValueError(f"unknown window {window!r}")

        ts = date + pd.Timedelta(
            hours=hour, minutes=random.randint(0, 59), seconds=random.randint(0, 59)
        )
        _records.append(
            {
                "phone_number": phone,
                "imei": imei,
                "area": area,
                "timestamp": ts,
                "call_type": random.choice(CALL_TYPES),
                "duration_seconds": random.randint(10, 600),
            }
        )


# --- User A: Consistent. Strong home + work plurality -> High confidence. ---
A = "01000001"
_add(A, "350000000000001", 17, "Hamra", "home")
_add(A, "350000000000001", 2, "Achrafieh", "home")
_add(A, "350000000000001", 1, "Verdun", "home")
_add(A, "350000000000001", 14, "Downtown", "work")
_add(A, "350000000000001", 3, "Achrafieh", "work")
_add(A, "350000000000001", 2, "Verdun", "work")
_add(A, "350000000000001", 1, "Hamra", "work")

# --- User B: Noisy but a real winner (~40-45%) -> Medium, never High. ---
B = "01000002"
_add(B, "350000000000002", 8, "Mazraa", "home")
_add(B, "350000000000002", 7, "Hamra", "home")
_add(B, "350000000000002", 5, "Verdun", "home")
_add(B, "350000000000002", 9, "Downtown", "work")
_add(B, "350000000000002", 6, "Hamra", "work")
_add(B, "350000000000002", 5, "Verdun", "work")

# --- User C: Sparse. 3 records, none in the home/work windows. ---
C = "01000003"
_add(C, "350000000000003", 3, "Hamra", "evening")

# --- User D: Adversarial. Near coin-flip home, scattered work. ---
D = "01000004"
_add(D, "350000000000004", 6, "Hamra", "home")  # 6/11 = 0.545 -> Medium, not High
_add(D, "350000000000004", 5, "Achrafieh", "home")
_add(D, "350000000000004", 4, "Downtown", "work")  # 4/12 = 0.33 -> Low
_add(D, "350000000000004", 3, "Mazraa", "work")
_add(D, "350000000000004", 3, "Verdun", "work")
_add(D, "350000000000004", 2, "Hamra", "work")

df = pd.DataFrame(
    _records,
    columns=[
        "phone_number",
        "imei",
        "area",
        "timestamp",
        "call_type",
        "duration_seconds",
    ],
)
df.to_csv(CSV_PATH, index=False)


# ---------------------------------------------------------------------------
# Independent ground-truth tally. Plain groupby/value_counts, NO detection.py.
# Same deterministic tie-break (count desc, earliest timestamp asc, area asc).
# ---------------------------------------------------------------------------
def _top_area(user_df: pd.DataFrame, window: str) -> str | None:
    if window == "home":
        w = user_df[user_df["timestamp"].dt.hour < 6]
    else:  # work
        hours = user_df["timestamp"].dt.hour
        w = user_df[(hours >= 9) & (hours < 18) & (user_df["timestamp"].dt.weekday < 5)]
    if len(w) == 0:
        return None
    g = w.groupby("area")["timestamp"].agg(["count", "min"]).sort_values(
        by=["count", "min", "area"], ascending=[False, True, True]
    )
    return str(g.index[0])


def _frequent(user_df: pd.DataFrame, top_n: int = 3) -> list[str]:
    g = user_df.groupby("area")["timestamp"].agg(["count", "min"]).sort_values(
        by=["count", "min", "area"], ascending=[False, True, True]
    )
    return [str(a) for a in g.head(top_n).index]


def _user(phone: str) -> pd.DataFrame:
    return df[df["phone_number"] == phone]


ground_truth = {
    # User A: exact area match + High confidence on both windows.
    A: {
        "home": {"expected_area": _top_area(_user(A), "home"), "expected_confidence": "High"},
        "work": {"expected_area": _top_area(_user(A), "work"), "expected_confidence": "High"},
        "frequent": _frequent(_user(A)),
    },
    # User B: exact area match AND confidence capped at Medium.
    B: {
        "home": {"expected_area": _top_area(_user(B), "home"), "max_confidence": "Medium"},
        "work": {"expected_area": _top_area(_user(B), "work"), "max_confidence": "Medium"},
        "frequent": _frequent(_user(B)),
    },
    # User C: too sparse to claim anything; just don't overstate confidence.
    C: {
        "home": {"expected_area": None, "max_confidence": "Low"},
        "work": {"expected_area": None, "max_confidence": "Low"},
    },
    # User D: must resist calling a near-coin-flip / scattered pattern "High".
    D: {
        "home": {"expected_area": None, "max_confidence": "Medium"},
        "work": {"expected_area": None, "max_confidence": "Low"},
    },
}

with open(GROUND_TRUTH_PATH, "w", encoding="utf-8") as fh:
    json.dump(ground_truth, fh, indent=2)
    fh.write("\n")

print(f"Wrote {len(df)} records to {os.path.basename(CSV_PATH)}")
print(f"Wrote ground truth for {len(ground_truth)} users to {os.path.basename(GROUND_TRUTH_PATH)}")
