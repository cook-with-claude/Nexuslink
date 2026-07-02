"""Per-row CDR validation for the import pipeline.

Reuses Phase 1's REQUIRED_COLUMNS / VALID_CALL_TYPES so import rules can never
drift from the algorithm. Phase 1 is imported read-only; nothing there is edited.
"""

from __future__ import annotations

import math

import pandas as pd

from app.infra.phase1 import REQUIRED_COLUMNS, VALID_CALL_TYPES

# Values that may be empty (Phase 1 treats these as optional).
_REQUIRED_NONEMPTY = ("phone_number", "area")


def missing_columns(columns: list[str]) -> list[str]:
    present = set(columns)
    return [c for c in REQUIRED_COLUMNS if c not in present]


def _is_blank(value) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return str(value).strip() == ""


def _parse_integer(value, field: str) -> tuple[int | None, str | None]:
    # Parse string values as exact integers first. Going straight through float()
    # loses precision past 2**53, so float("9223372036854775807") rounds UP to
    # ...808.0 -- which would defeat the int64 range guard in validate_row (the
    # true max would be reported as out-of-range). int() is exact for any
    # magnitude. Fractional/scientific strings ("1.5", "42.0", "1e3") raise here
    # and fall through to the float path below, which detects and normalizes them.
    if isinstance(value, str):
        # int() and float() accept PEP-515 underscores ("1_1" == 11), but Phase 1's
        # loader parses with pd.to_numeric, which does not -- such a row would import
        # here yet be dropped by the frozen algorithm's own loader. Reject for parity.
        if "_" in value:
            return None, f"invalid {field}"
        try:
            return int(value), None
        except ValueError:
            pass
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None, f"invalid {field}"
    if not math.isfinite(parsed) or not parsed.is_integer():
        return None, f"invalid {field}"
    return int(parsed), None


def validate_row(row: dict) -> tuple[dict | None, str | None]:
    for field in _REQUIRED_NONEMPTY:
        value = row.get(field)
        if _is_blank(value):
            return None, f"{field} is required"

    # Pin the format to ISO-8601 rather than letting pandas infer it. Inference
    # would silently misread locale formats (e.g. DD/MM/YYYY) where day <= 12 and
    # coerce the rest to NaT -- partly wrong, partly dropped, with no signal. The
    # DB stores timestamps as .isoformat(), so ISO-8601 is the natural contract.
    ts = pd.to_datetime(row.get("timestamp"), errors="coerce", format="ISO8601")
    if pd.isna(ts):
        return None, "unparseable timestamp"
    # Phase 1's time-window logic (home/work) works on naive local wall-clock
    # times. A tz-aware timestamp would be stored with its offset and, once a
    # dataset mixes offsets, pandas can no longer build a datetime column -- the
    # detectors' .dt.hour access then raises at analyze time. Reject here so the
    # bad row is skipped at import rather than poisoning a later analysis.
    if ts.tzinfo is not None:
        return None, "timezone-aware timestamp not supported (expected naive local time)"

    call_type, reason = _parse_integer(row.get("call_type"), "call_type")
    if reason is not None:
        return None, reason
    if call_type not in VALID_CALL_TYPES:
        return None, f"call_type {call_type} not in {sorted(VALID_CALL_TYPES)}"

    duration, reason = _parse_integer(row.get("duration_seconds"), "duration_seconds")
    if reason is not None:
        return None, reason
    if duration < 0:
        return None, "negative duration_seconds"
    # SQLite stores INTEGERs as signed 64-bit; a larger value makes the bulk
    # executemany raise OverflowError and abort the ENTIRE import. Skip the one
    # offending row instead.
    if duration > 9_223_372_036_854_775_807:
        return None, "duration_seconds out of range"

    def _s(v):
        return None if _is_blank(v) else str(v).strip()

    clean = {
        "phone_number": str(row["phone_number"]).strip(),
        "imei": _s(row.get("imei")),
        "area": str(row["area"]).strip(),
        "timestamp": ts.isoformat(),
        "call_type": call_type,
        "duration_seconds": duration,
        "other_party": _s(row.get("other_party")),
        "other_imei": _s(row.get("other_imei")),
        "other_area": _s(row.get("other_area")),
    }
    return clean, None
