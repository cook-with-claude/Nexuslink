"""Per-row CDR validation for the import pipeline.

Reuses Phase 1's REQUIRED_COLUMNS / VALID_CALL_TYPES so import rules can never
drift from the algorithm. Phase 1 is imported read-only; nothing there is edited.
"""

from __future__ import annotations

import os
import sys

import pandas as pd

# Make the frozen phase1_cdr package importable without modifying it.
_PHASE1 = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "phase1_cdr")
if _PHASE1 not in sys.path:
    sys.path.insert(0, _PHASE1)

from loader import REQUIRED_COLUMNS, VALID_CALL_TYPES  # noqa: E402

# Values that may be empty (Phase 1 treats these as optional).
_REQUIRED_NONEMPTY = ("phone_number", "area")


def missing_columns(columns: list[str]) -> list[str]:
    present = set(columns)
    return [c for c in REQUIRED_COLUMNS if c not in present]


def validate_row(row: dict) -> tuple[dict | None, str | None]:
    for field in _REQUIRED_NONEMPTY:
        value = row.get(field)
        if value is None or str(value).strip() == "":
            return None, f"{field} is required"

    ts = pd.to_datetime(row.get("timestamp"), errors="coerce")
    if pd.isna(ts):
        return None, "unparseable timestamp"

    try:
        call_type = int(float(row.get("call_type")))
    except (TypeError, ValueError):
        return None, "invalid call_type"
    if call_type not in VALID_CALL_TYPES:
        return None, f"call_type {call_type} not in {sorted(VALID_CALL_TYPES)}"

    try:
        duration = int(float(row.get("duration_seconds")))
    except (TypeError, ValueError):
        return None, "invalid duration_seconds"
    if duration < 0:
        return None, "negative duration_seconds"

    def _s(v):
        return None if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)

    clean = {
        "phone_number": str(row["phone_number"]),
        "imei": _s(row.get("imei")),
        "area": str(row["area"]),
        "timestamp": ts.isoformat(),
        "call_type": call_type,
        "duration_seconds": duration,
        "other_party": _s(row.get("other_party")),
        "other_imei": _s(row.get("other_imei")),
        "other_area": _s(row.get("other_area")),
    }
    return clean, None
