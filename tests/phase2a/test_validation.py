from app.datasets import validation


def test_missing_columns_detected():
    cols = ["phone_number", "imei", "area", "timestamp", "call_type"]  # missing 4
    missing = validation.missing_columns(cols)
    assert "duration_seconds" in missing
    assert "other_party" in missing


def test_valid_row_passes_and_normalizes_timestamp():
    row = {
        "phone_number": "01000001", "imei": "350", "area": "Hamra",
        "timestamp": "2024-01-01 03:15:00", "call_type": "1",
        "duration_seconds": "42", "other_party": "03200101",
        "other_imei": "350", "other_area": "Hamra",
    }
    clean, reason = validation.validate_row(row)
    assert reason is None
    assert clean["call_type"] == 1
    assert clean["duration_seconds"] == 42
    assert clean["timestamp"].startswith("2024-01-01T03:15:00")


def test_bad_call_type_skipped():
    row = {"phone_number": "x", "area": "Hamra", "timestamp": "2024-01-01 03:00:00",
           "call_type": "7", "duration_seconds": "5"}
    clean, reason = validation.validate_row(row)
    assert clean is None and "call_type" in reason


def test_fractional_call_type_skipped():
    row = {"phone_number": "x", "area": "Hamra", "timestamp": "2024-01-01 03:00:00",
           "call_type": "1.5", "duration_seconds": "5"}
    clean, reason = validation.validate_row(row)
    assert clean is None and "call_type" in reason


def test_unparseable_timestamp_skipped():
    row = {"phone_number": "x", "area": "Hamra", "timestamp": "not-a-date",
           "call_type": "1", "duration_seconds": "5"}
    clean, reason = validation.validate_row(row)
    assert clean is None and "timestamp" in reason


def test_non_iso_locale_date_is_rejected_not_misparsed():
    """A DD/MM/YYYY date is non-ISO and must be rejected deterministically rather
    than silently misread (day<=12) or partially coerced to NaT."""
    row = {"phone_number": "x", "area": "Hamra", "timestamp": "13/06/2026 08:00:00",
           "call_type": "1", "duration_seconds": "5"}
    clean, reason = validation.validate_row(row)
    assert clean is None and "timestamp" in reason


def test_iso_timestamp_with_t_separator_accepted():
    row = {"phone_number": "x", "area": "Hamra", "timestamp": "2024-01-01T03:15:00",
           "call_type": "1", "duration_seconds": "5"}
    clean, reason = validation.validate_row(row)
    assert reason is None
    assert clean["timestamp"].startswith("2024-01-01T03:15:00")


def test_negative_duration_skipped():
    row = {"phone_number": "x", "area": "Hamra", "timestamp": "2024-01-01 03:00:00",
           "call_type": "1", "duration_seconds": "-3"}
    clean, reason = validation.validate_row(row)
    assert clean is None and "duration" in reason


def test_fractional_duration_skipped():
    row = {"phone_number": "x", "area": "Hamra", "timestamp": "2024-01-01 03:00:00",
           "call_type": "1", "duration_seconds": "2.5"}
    clean, reason = validation.validate_row(row)
    assert clean is None and "duration" in reason


def test_missing_required_field_skipped():
    row = {"phone_number": "", "area": "Hamra", "timestamp": "2024-01-01 03:00:00",
           "call_type": "1", "duration_seconds": "5"}
    clean, reason = validation.validate_row(row)
    assert clean is None and "phone_number" in reason


def test_nan_required_field_skipped():
    row = {"phone_number": float("nan"), "area": "Hamra",
           "timestamp": "2024-01-01 03:00:00", "call_type": "1",
           "duration_seconds": "5"}
    clean, reason = validation.validate_row(row)
    assert clean is None and "phone_number" in reason
