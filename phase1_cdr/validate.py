"""Validation harness: compare detector output against a known ground truth.

This module never generates ground truth -- it only consumes the ground-truth
JSON and checks the detectors against it. Each check produces a row-dict so the
results can be rendered as a table by main.py.
"""

from __future__ import annotations

from typing import Dict, List

import pandas as pd

from detection import (
    CONFIDENCE_ORDER,
    DetectionResult,
    detect_frequent_areas,
    detect_frequent_confidence,
    detect_home,
    detect_work,
)


def _check_confidence(result: DetectionResult, spec: dict, failures: List[str]) -> None:
    """Apply exact/ceiling confidence rules (shared by window + frequent)."""
    if "expected_confidence" in spec:
        if result.confidence != spec["expected_confidence"]:
            failures.append("confidence")
    elif "max_confidence" in spec:
        ceiling = CONFIDENCE_ORDER[spec["max_confidence"]]
        if CONFIDENCE_ORDER[result.confidence] > ceiling:
            failures.append("confidence")


def _check_window(test_name: str, user: str, result: DetectionResult, spec: dict) -> dict:
    """Apply the independent area + confidence + alternatives rules."""
    failures: List[str] = []

    # --- Area check (independent of confidence) ---
    if "expected_area" in spec:
        expected_area = spec["expected_area"]
        if expected_area is not None:
            if result.area != expected_area:
                failures.append("area")
        else:
            has_conf_field = "expected_confidence" in spec or "max_confidence" in spec
            if not has_conf_field and result.area is not None:
                failures.append("area")

    # --- Confidence check ---
    _check_confidence(result, spec, failures)

    # --- Alternatives check (only when the spec pins them) ---
    if "expected_alternatives" in spec:
        if sorted(result.alternatives) != sorted(spec["expected_alternatives"]):
            failures.append("alternatives")

    expected_parts = []
    if "expected_area" in spec:
        expected_parts.append(f"area={spec['expected_area']!r}")
    if "expected_confidence" in spec:
        expected_parts.append(f"conf=={spec['expected_confidence']}")
    if "max_confidence" in spec:
        expected_parts.append(f"conf<={spec['max_confidence']}")
    if "expected_alternatives" in spec:
        expected_parts.append(f"alts={spec['expected_alternatives']}")

    return {
        "user": user,
        "test": test_name,
        "expected": ", ".join(expected_parts),
        "detected": repr(result.area),
        "confidence": result.confidence_label,
        "alternatives": str(result.alternatives),
        "result": "PASS" if not failures else "FAIL (" + ", ".join(failures) + ")",
    }


def _check_frequent(user: str, areas: List[str], lead: DetectionResult, spec: dict) -> dict:
    """Check the ranked list order plus the lead area's confidence ceiling."""
    failures: List[str] = []
    expected_areas = spec["expected_areas"] if isinstance(spec, dict) else spec
    if areas != expected_areas:
        failures.append("order/areas")
    if isinstance(spec, dict):
        _check_confidence(lead, spec, failures)

    return {
        "user": user,
        "test": "frequent",
        "expected": str(expected_areas),
        "detected": str(areas),
        "confidence": lead.confidence_label,
        "alternatives": str(lead.alternatives),
        "result": "PASS" if not failures else "FAIL (" + ", ".join(failures) + ")",
    }


def validate(df: pd.DataFrame, ground_truth: Dict[str, dict]) -> List[dict]:
    """Run all detectors for every user in ground_truth and return row-dicts."""
    rows: List[dict] = []

    for user, spec in ground_truth.items():
        user_df = df[df["phone_number"] == user]

        if "home" in spec:
            rows.append(_check_window("home", user, detect_home(user_df), spec["home"]))
        if "work" in spec:
            rows.append(_check_window("work", user, detect_work(user_df), spec["work"]))
        if "frequent" in spec:
            areas = [area for area, _c, _s in detect_frequent_areas(user_df)]
            lead = detect_frequent_confidence(user_df)
            rows.append(_check_frequent(user, areas, lead, spec["frequent"]))

    return rows
