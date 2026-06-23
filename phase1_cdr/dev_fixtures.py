"""Throwaway development fixture generator.

Deterministically builds a synthetic CDR dataset (sample_data.csv) and an
independently-computed ground truth (ground_truth.json) for five test users at
REALISTIC per-subscriber volume (most users carry 500-5000 total calls).

IMPORTANT:
  * All data here is synthetic, produced with a fixed seed. No real telecom
    data and no LLM is ever involved.
  * This file is disposable. The team's real generator will replace it and
    must emit the same 6-column schema.
  * ground_truth.json is computed by a LOCAL tally (plain groupby) below --
    it deliberately does NOT import detection.py, so validating detection.py
    against this file actually proves something.

The five users are archetypes chosen to exercise every gate of the four-gate,
weakest-link confidence model, and each is given a DIFFERENT observation span so
the relative Density gate actually discriminates:

  A  Consistent commuter  ~365-day span, dense  -> home/work/frequent High
  B  Noisy, contested      ~180-day span        -> home Low, work Medium
  C  Sparse floor case     ~3-week span, ~40 records, no window data -> Insufficient
  D  Adversarial near-tie  ~180-day span        -> home <=Medium, work <=Low
  E  Long-span, sparse window  ~365-day span     -> Density is the SOLE binder

C is deliberately tiny -- it is the small-sample floor test, the one archetype
intentionally exempt from the 500-5000 volume target. E is the new user that
finally exercises Density in the harness: it is well-observed overall (~600
calls across a full year) but calls overnight only ~30 times, so N/Share/
Closeness all read strong while Density alone caps the home result to Low.
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

CALL_TYPES = [1, 2, 11, 22]

# Counterparty assignment uses its OWN RNG instance, kept entirely separate from
# the main `random`/`np.random` streams. This is deliberate: it means the dates,
# hours, call_types and areas of every record are byte-identical to the
# pre-contacts fixtures, so the existing home/work/frequent/confidence ground
# truth (and the verified 12/12 + 13-passed state) is unchanged -- only the new
# counterparty columns and the contacts ground-truth block are added.
_contact_rng = random.Random(20240623)

# Per-user counterparty pools: (number, imei, area, weight). The weight only
# steers how often a contact is drawn; the ground truth tallies whatever
# actually lands in the data, so the ranking is self-consistent regardless of
# weights or ties. A contact keeps the same imei/area across all its rows.
# Users A and D carry 6 contacts so the top_n=5 cap is exercised.
CONTACTS: dict[str, list[tuple[str, str, str, int]]] = {
    "01000001": [  # A: one clear primary, long tail
        ("03200101", "350000000000201", "Hamra", 50),
        ("03200102", "350000000000202", "Downtown", 28),
        ("03200103", "350000000000203", "Achrafieh", 16),
        ("03200104", "350000000000204", "Verdun", 9),
        ("03200105", "350000000000205", "Mazraa", 5),
        ("03200106", "350000000000206", "Hamra", 2),
    ],
    "01000002": [  # B
        ("03200201", "350000000000211", "Mazraa", 40),
        ("03200202", "350000000000212", "Hamra", 30),
        ("03200203", "350000000000213", "Verdun", 20),
        ("03200204", "350000000000214", "Downtown", 12),
        ("03200205", "350000000000215", "Achrafieh", 6),
    ],
    "01000003": [  # C (sparse)
        ("03200301", "350000000000301", "Hamra", 20),
        ("03200302", "350000000000302", "Achrafieh", 10),
        ("03200303", "350000000000303", "Verdun", 5),
    ],
    "01000004": [  # D
        ("03200401", "350000000000401", "Hamra", 35),
        ("03200402", "350000000000402", "Achrafieh", 33),
        ("03200403", "350000000000403", "Downtown", 18),
        ("03200404", "350000000000404", "Mazraa", 10),
        ("03200405", "350000000000405", "Verdun", 8),
        ("03200406", "350000000000406", "Hamra", 4),
    ],
    "01000005": [  # E
        ("03200501", "350000000000501", "Hamra", 45),
        ("03200502", "350000000000502", "Hamra", 25),
        ("03200503", "350000000000503", "Downtown", 12),
        ("03200504", "350000000000504", "Verdun", 6),
    ],
}

_records: list[dict] = []


def _date_pool(start: str, ndays: int) -> tuple[list[pd.Timestamp], list[pd.Timestamp]]:
    """Return (all_dates, weekday_dates) for an ndays span starting at `start`."""
    base = pd.Timestamp(start)
    all_dates = [base + pd.Timedelta(days=d) for d in range(ndays)]
    weekday_dates = [d for d in all_dates if d.weekday() < 5]
    return all_dates, weekday_dates


def _add(
    phone: str,
    imei: str,
    n: int,
    area: str,
    window: str,
    all_dates: list[pd.Timestamp],
    weekday_dates: list[pd.Timestamp],
) -> None:
    """Append n synthetic records for one user/area in a given time window.

    The date is drawn from the user's own observation span (`all_dates`), so each
    user can be observed for a different length of time -- which is what gives the
    Density gate something to discriminate on.

    The counterparty (other_party/imei/area) is drawn from the user's contact
    pool using the SEPARATE `_contact_rng`, so it never perturbs the main data
    stream the existing ground truth depends on.
    """
    pool = CONTACTS[phone]
    weights = [c[3] for c in pool]
    for _ in range(n):
        if window == "home":  # hour in [0, 6), any day
            date = random.choice(all_dates)
            hour = random.randint(0, 5)
        elif window == "work":  # hour in [9, 18), weekdays only
            date = random.choice(weekday_dates)
            hour = random.randint(9, 17)
        elif window == "evening":  # outside both windows
            date = random.choice(all_dates)
            hour = random.randint(19, 23)
        else:
            raise ValueError(f"unknown window {window!r}")

        ts = date + pd.Timedelta(
            hours=hour, minutes=random.randint(0, 59), seconds=random.randint(0, 59)
        )
        other_party, other_imei, other_area, _w = pool[
            _contact_rng.choices(range(len(pool)), weights=weights, k=1)[0]
        ]
        _records.append(
            {
                "phone_number": phone,
                "imei": imei,
                "area": area,
                "timestamp": ts,
                "call_type": random.choice(CALL_TYPES),
                "duration_seconds": random.randint(10, 600),
                "other_party": other_party,
                "other_imei": other_imei,
                "other_area": other_area,
            }
        )


# --- User A: Consistent commuter. ~365-day span, dense overnight + weekday-day.
# Strong home (Hamra) and work (Downtown) plurality, many active days -> every
# gate High. Hamra is also the overall plurality -> frequent High. ~1060 calls.
A = "01000001"
A_all, A_wk = _date_pool("2024-01-01", 365)
_add(A, "350000000000001", 560, "Hamra", "home", A_all, A_wk)
_add(A, "350000000000001", 50, "Achrafieh", "home", A_all, A_wk)
_add(A, "350000000000001", 30, "Verdun", "home", A_all, A_wk)
_add(A, "350000000000001", 360, "Downtown", "work", A_all, A_wk)
_add(A, "350000000000001", 40, "Achrafieh", "work", A_all, A_wk)
_add(A, "350000000000001", 20, "Verdun", "work", A_all, A_wk)

# --- User B: Noisy but with a real winner (~42%). ~180-day span. Home is a
# near-tie (Mazraa just ahead of Hamra) so Closeness drags it to Low; the ground
# truth only asserts the ceiling (<=Medium) and the Hamra alternative. ~990 calls.
B = "01000002"
B_all, B_wk = _date_pool("2024-01-01", 181)
_add(B, "350000000000002", 210, "Mazraa", "home", B_all, B_wk)
_add(B, "350000000000002", 180, "Hamra", "home", B_all, B_wk)
_add(B, "350000000000002", 110, "Verdun", "home", B_all, B_wk)
_add(B, "350000000000002", 220, "Downtown", "work", B_all, B_wk)
_add(B, "350000000000002", 140, "Hamra", "work", B_all, B_wk)
_add(B, "350000000000002", 130, "Verdun", "work", B_all, B_wk)

# --- User C: Sparse floor case. ~3-week span, ~40 evening records, NONE in the
# home/work windows -> both window detectors return Insufficient data. The one
# archetype deliberately kept below the volume target (it tests the N floor).
C = "01000003"
C_all, C_wk = _date_pool("2024-01-01", 21)
_add(C, "350000000000003", 40, "Hamra", "evening", C_all, C_wk)

# --- User D: Adversarial. ~180-day span. Home is a near coin-flip (Hamra vs
# Achrafieh) and work is scattered with no dominant area -> home <=Medium with an
# Achrafieh alternative, work <=Low with two alternatives. ~1010 calls.
D = "01000004"
D_all, D_wk = _date_pool("2024-01-01", 181)
_add(D, "350000000000004", 260, "Hamra", "home", D_all, D_wk)
_add(D, "350000000000004", 230, "Achrafieh", "home", D_all, D_wk)
_add(D, "350000000000004", 160, "Downtown", "work", D_all, D_wk)
_add(D, "350000000000004", 140, "Mazraa", "work", D_all, D_wk)
_add(D, "350000000000004", 130, "Verdun", "work", D_all, D_wk)
_add(D, "350000000000004", 90, "Hamra", "work", D_all, D_wk)

# --- User E: Long-span, sparse window. ~365-day span. Well-observed overall
# (~570 evening calls), but only ~30 unanimous Hamra overnight calls scattered
# across the whole year. N (>=15) -> Medium, Share 100% -> High, Closeness 0 ->
# High, but ~30 active nights / 365 days -> coverage ~0.08 -> Density LOW. Density
# is therefore the SOLE binding gate, so the home result is exactly Low. This is
# the user that finally exercises Density in the harness; the review gate trace
# should confirm Density is the sole binder, since confidence alone cannot encode
# which gate produced the cap.
E = "01000005"
E_all, E_wk = _date_pool("2024-01-01", 365)
_add(E, "350000000000005", 30, "Hamra", "home", E_all, E_wk)
_add(E, "350000000000005", 570, "Hamra", "evening", E_all, E_wk)

df = pd.DataFrame(
    _records,
    columns=[
        "phone_number",
        "imei",
        "area",
        "timestamp",
        "call_type",
        "duration_seconds",
        "other_party",
        "other_imei",
        "other_area",
    ],
)
df.to_csv(CSV_PATH, index=False)


# ---------------------------------------------------------------------------
# Independent ground-truth tally. Plain groupby/value_counts, NO detection.py.
# Same deterministic tie-break (count desc, earliest timestamp asc, area asc).
# ---------------------------------------------------------------------------
def _window(user_df: pd.DataFrame, window: str) -> pd.DataFrame:
    if window == "home":
        return user_df[user_df["timestamp"].dt.hour < 6]
    hours = user_df["timestamp"].dt.hour
    return user_df[(hours >= 9) & (hours < 18) & (user_df["timestamp"].dt.weekday < 5)]


def _ranked(frame: pd.DataFrame) -> list[tuple[str, int]]:
    g = frame.groupby("area")["timestamp"].agg(["count", "min"]).sort_values(
        by=["count", "min", "area"], ascending=[False, True, True]
    )
    return [(str(a), int(r["count"])) for a, r in g.iterrows()]


def _top_area(user_df: pd.DataFrame, window: str) -> str | None:
    ranked = _ranked(_window(user_df, window))
    return ranked[0][0] if ranked else None


def _alternatives(user_df: pd.DataFrame, window: str) -> list[str]:
    """Areas within the >70% near-tie band of the winner (independent tally)."""
    ranked = _ranked(_window(user_df, window))
    if not ranked:
        return []
    top_count = ranked[0][1]
    return [a for a, c in ranked[1:] if c > 0.70 * top_count]


def _frequent(user_df: pd.DataFrame, top_n: int = 5) -> list[str]:
    return [a for a, _c in _ranked(user_df)[:top_n]]


def _contacts(user_df: pd.DataFrame, top_n: int = 5) -> list[dict]:
    """Independently tally the subject's top counterparties (no detection.py).

    Groups by other_party, counts the total plus a 4-way split by call_type,
    and ranks total desc -> earliest timestamp asc -> number asc (the same
    deterministic tie-break the detector uses)."""
    if len(user_df) == 0:
        return []
    ranked: list[tuple[int, pd.Timestamp, str, dict]] = []
    for number, sub in user_df.groupby("other_party"):
        types = sub["call_type"]
        ranked.append(
            (
                int(len(sub)),
                sub["timestamp"].min(),
                str(number),
                {
                    "number": str(number),
                    "total": int(len(sub)),
                    "call_out": int((types == 1).sum()),
                    "call_in": int((types == 2).sum()),
                    "sms_out": int((types == 11).sum()),
                    "sms_in": int((types == 22).sum()),
                },
            )
        )
    ranked.sort(key=lambda r: (-r[0], r[1], r[2]))
    return [r[3] for r in ranked[:top_n]]


def _user(phone: str) -> pd.DataFrame:
    return df[df["phone_number"] == phone]


ground_truth = {
    # User A: exact area match + High confidence on both windows and frequent.
    A: {
        "home": {"expected_area": _top_area(_user(A), "home"), "expected_confidence": "High"},
        "work": {"expected_area": _top_area(_user(A), "work"), "expected_confidence": "High"},
        "frequent": {"expected_areas": _frequent(_user(A)), "max_confidence": "High"},
        "contacts": _contacts(_user(A)),
    },
    # User B: real winner, but a noisy near-tie -> capped at Medium, alternatives listed.
    B: {
        "home": {
            "expected_area": _top_area(_user(B), "home"),
            "max_confidence": "Medium",
            "expected_alternatives": _alternatives(_user(B), "home"),
        },
        "work": {"expected_area": _top_area(_user(B), "work"), "max_confidence": "Medium"},
        "frequent": {"expected_areas": _frequent(_user(B)), "max_confidence": "Medium"},
        "contacts": _contacts(_user(B)),
    },
    # User C: no home/work window records, so the detector should return no area
    # and exact Insufficient data, not merely a low-confidence guess.
    C: {
        "home": {"expected_area": None, "expected_confidence": "Insufficient data"},
        "work": {"expected_area": None, "expected_confidence": "Insufficient data"},
        "contacts": _contacts(_user(C)),
    },
    # User D: names the plurality area, but must resist High and flag the near-tie.
    D: {
        "home": {
            "expected_area": _top_area(_user(D), "home"),
            "max_confidence": "Medium",
            "expected_alternatives": _alternatives(_user(D), "home"),
        },
        "work": {
            "expected_area": _top_area(_user(D), "work"),
            "max_confidence": "Low",
            "expected_alternatives": _alternatives(_user(D), "work"),
        },
        "contacts": _contacts(_user(D)),
    },
    # User E: clean unanimous home area, but Density alone caps it. Pinned EXACTLY
    # to Low (not a ceiling); the separate gate trace/unit tests establish that
    # Density is the sole binding gate.
    E: {
        "home": {"expected_area": _top_area(_user(E), "home"), "expected_confidence": "Low"},
        "work": {"expected_area": None, "expected_confidence": "Insufficient data"},
        "contacts": _contacts(_user(E)),
    },
}

with open(GROUND_TRUTH_PATH, "w", encoding="utf-8") as fh:
    json.dump(ground_truth, fh, indent=2)
    fh.write("\n")

print(f"Wrote {len(df)} records to {os.path.basename(CSV_PATH)}")
print(f"Wrote ground truth for {len(ground_truth)} users to {os.path.basename(GROUND_TRUTH_PATH)}")
