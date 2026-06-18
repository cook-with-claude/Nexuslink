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
    detect_home,
    detect_work,
)


def _check_window(test_name: str, user: str, result: DetectionResult, spec: dict) -> dict:
    """Apply the independent area + confidence rules for a home/work spec."""
    failures: List[str] = []

    # --- Area check (independent of confidence) ---
    if "expected_area" in spec:
        expected_area = spec["expected_area"]
        if expected_area is not None:
            # A specific area is required: exact match.
            if result.area != expected_area:
                failures.append("area")
        else:
            # expected_area is null.
            has_conf_field = "expected_confidence" in spec or "max_confidence" in spec
            if not has_conf_field:
                # "found nothing" case -- detected area must be None.
                if result.area is not None:
                    failures.append("area")
            # else: a confidence field is present -> skip the area check entirely.

    # --- Confidence check (independent of area) ---
    if "expected_confidence" in spec:
        if result.confidence != spec["expected_confidence"]:
            failures.append("confidence")
    elif "max_confidence" in spec:
        ceiling = CONFIDENCE_ORDER[spec["max_confidence"]]
        if CONFIDENCE_ORDER[result.confidence] > ceiling:
            failures.append("confidence")

    # Build a readable "expected" description.
    expected_parts = []
    if "expected_area" in spec:
        expected_parts.append(f"area={spec['expected_area']!r}")
    if "expected_confidence" in spec:
        expected_parts.append(f"conf=={spec['expected_confidence']}")
    if "max_confidence" in spec:
        expected_parts.append(f"conf<={spec['max_confidence']}")

    return {
        "user": user,
        "test": test_name,
        "expected": ", ".join(expected_parts),
        "detected": repr(result.area),
        "confidence": result.confidence,
        "result": "PASS" if not failures else "FAIL (" + ", ".join(failures) + ")",
    }


def _check_frequent(user: str, detected_areas: List[str], expected: List[str]) -> dict:
    ok = detected_areas == expected
    return {
        "user": user,
        "test": "frequent",
        "expected": str(expected),
        "detected": str(detected_areas),
        "confidence": "",
        "result": "PASS" if ok else "FAIL (order/areas)",
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
            detected = [area for area, _count, _share in detect_frequent_areas(user_df)]
            rows.append(_check_frequent(user, detected, spec["frequent"]))

    return rows
