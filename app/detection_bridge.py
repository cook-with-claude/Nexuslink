"""The ONLY seam between the backend and the frozen Phase 1 algorithm.

Pulls a subject's stored CDR rows, rebuilds the DataFrame shape Phase 1 expects,
runs the five detectors, and serializes their dataclasses to JSON-ready dicts.
Phase 1 is imported read-only; nothing under phase1_cdr/ is modified.
"""

from __future__ import annotations

import os
import sys

import pandas as pd

_PHASE1 = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "phase1_cdr")
if _PHASE1 not in sys.path:
    sys.path.insert(0, _PHASE1)

import detection  # noqa: E402

_COLUMNS = [
    "phone_number", "imei", "area", "timestamp", "call_type",
    "duration_seconds", "other_party", "other_imei", "other_area",
]


def rows_to_frame(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(list(rows), columns=_COLUMNS)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["call_type"] = pd.to_numeric(df["call_type"], errors="coerce").astype("Int64").astype(int)
    df["duration_seconds"] = pd.to_numeric(df["duration_seconds"], errors="coerce").fillna(0).astype(int)
    return df


def _result_to_dict(r: "detection.DetectionResult") -> dict:
    return {
        "area": r.area,
        "confidence": r.confidence,
        "confidence_label": r.confidence_label,
        "near_tie": r.near_tie,
        "alternatives": list(r.alternatives),
        "supporting_records": r.supporting_records,
        "total_window_records": r.total_window_records,
        "share": r.share,
        "closeness": r.closeness,
        "density": r.density,
        "gates": r.gates,
    }


def _contact_to_dict(c: "detection.ContactRank") -> dict:
    return {
        "number": c.number, "total": c.total, "call_out": c.call_out,
        "call_in": c.call_in, "sms_out": c.sms_out, "sms_in": c.sms_in,
    }


def analyze_frame(df: pd.DataFrame, top_n: int = 5) -> dict:
    freq_areas = detection.detect_frequent_areas(df, top_n=top_n)
    return {
        "home": _result_to_dict(detection.detect_home(df)),
        "work": _result_to_dict(detection.detect_work(df)),
        "frequent_areas": [
            {"area": a, "count": c, "share": s} for a, c, s in freq_areas
        ],
        "frequent_areas_confidence": _result_to_dict(detection.detect_frequent_confidence(df)),
        "frequent_contacts": [
            _contact_to_dict(c) for c in detection.detect_frequent_contacts(df, top_n=top_n)
        ],
    }
