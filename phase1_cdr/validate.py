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
    detect_frequent_contacts,
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
        elif result.area is not None:
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


def _check_frequent(
    user: str, freq: List[tuple], lead: DetectionResult, spec: dict
) -> dict:
    """Check the ranked list order plus the lead area's confidence ceiling.

    `freq` is the (area, count, share) output of detect_frequent_areas; the share
    is surfaced as a percentage in the detected column.
    """
    failures: List[str] = []
    areas = [area for area, _c, _s in freq]
    expected_areas = spec["expected_areas"] if isinstance(spec, dict) else spec
    if areas != expected_areas:
        failures.append("order/areas")
    if isinstance(spec, dict):
        _check_confidence(lead, spec, failures)

    detected = ", ".join(f"{area} {share * 100:.0f}%" for area, _c, share in freq)

    return {
        "user": user,
        "test": "frequent",
        "expected": str(expected_areas),
        "detected": detected,
        "confidence": lead.confidence_label,
        "alternatives": str(lead.alternatives),
        "result": "PASS" if not failures else "FAIL (" + ", ".join(failures) + ")",
    }


def _contact_to_dict(contact) -> dict:
    return {
        "number": contact.number,
        "total": contact.total,
        "call_out": contact.call_out,
        "call_in": contact.call_in,
        "sms_out": contact.sms_out,
        "sms_in": contact.sms_in,
    }


def validate_contacts(df: pd.DataFrame, ground_truth: Dict[str, dict]) -> List[dict]:
    """Compare each subject's ranked contacts against the ground truth.

    Returns one row per contact rank (so the 4-way breakdown is visible), with a
    PASS/FAIL per rank. Length mismatches surface as missing/extra rows.
    """
    rows: List[dict] = []
    for user, spec in ground_truth.items():
        if "contacts" not in spec:
            continue
        expected = spec["contacts"]
        user_df = df[df["phone_number"] == user]
        detected = [_contact_to_dict(c) for c in detect_frequent_contacts(user_df)]

        for rank in range(max(len(expected), len(detected))):
            exp = expected[rank] if rank < len(expected) else None
            det = detected[rank] if rank < len(detected) else None
            if det is None:
                result, show = "FAIL (missing)", exp
            elif exp is None:
                result, show = "FAIL (extra)", det
            elif det == exp:
                result, show = "PASS", det
            else:
                result, show = "FAIL (mismatch)", det
            rows.append({
                "user": user,
                "rank": rank + 1,
                "number": show["number"],
                "total": show["total"],
                "call_out": show["call_out"],
                "call_in": show["call_in"],
                "sms_out": show["sms_out"],
                "sms_in": show["sms_in"],
                "result": result,
            })
    return rows


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
            freq = detect_frequent_areas(user_df)
            lead = detect_frequent_confidence(user_df)
            rows.append(_check_frequent(user, freq, lead, spec["frequent"]))

    return rows
