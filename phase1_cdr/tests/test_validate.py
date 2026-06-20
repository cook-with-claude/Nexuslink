"""Unit tests for validation harness contracts."""

from __future__ import annotations

from detection import DetectionResult
from validate import _check_window


def test_expected_area_none_is_enforced_with_confidence_ceiling():
    result = DetectionResult(area="Hamra", confidence="Low")

    row = _check_window(
        "home",
        "01000000",
        result,
        {"expected_area": None, "max_confidence": "Low"},
    )

    assert row["result"] == "FAIL (area)"


def test_expected_area_none_passes_for_true_no_area():
    result = DetectionResult(area=None, confidence="Insufficient data")

    row = _check_window(
        "home",
        "01000000",
        result,
        {"expected_area": None, "max_confidence": "Low"},
    )

    assert row["result"] == "PASS"
