"""CDR file loading and schema validation.

Reads a Call Detail Record file (CSV/Excel) into a validated pandas DataFrame.
This module performs only structural validation and cleaning -- no pattern
detection, no I/O beyond reading the given file. All data is synthetic.
"""

from __future__ import annotations

import os

import pandas as pd

REQUIRED_COLUMNS = [
    "phone_number",
    "imei",
    "area",
    "timestamp",
    "call_type",
    "duration_seconds",
]

VALID_CALL_TYPES = {1, 2, 11, 22}

# phone_number and imei are kept as strings so leading zeros survive and large
# numbers never get coerced into scientific notation.
_STRING_COLUMNS = {"phone_number": str, "imei": str}

_SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xls"}


class CDRValidationError(Exception):
    """Raised when a CDR file cannot be loaded due to a schema problem."""


def load_cdr(path: str) -> pd.DataFrame:
    """Load and validate a CDR file into a DataFrame.

    Raises CDRValidationError for unsupported file types or missing columns.
    Rows with unparseable timestamps or invalid call_type values are dropped
    with a one-line warning each.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext not in _SUPPORTED_EXTENSIONS:
        raise CDRValidationError("Unsupported file type")

    if ext == ".csv":
        df = pd.read_csv(path, dtype=_STRING_COLUMNS)
    else:
        df = pd.read_excel(path, dtype=_STRING_COLUMNS, engine="openpyxl")

    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise CDRValidationError(
            "Missing required column(s): " + ", ".join(missing)
        )

    # Drop rows whose timestamp cannot be parsed.
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    bad_timestamps = int(df["timestamp"].isna().sum())
    if bad_timestamps:
        print(f"Warning: dropped {bad_timestamps} row(s) with unparseable timestamps")
        df = df[df["timestamp"].notna()]

    # Drop rows whose call_type is not one of the valid codes.
    call_type = pd.to_numeric(df["call_type"], errors="coerce")
    valid_mask = call_type.isin(VALID_CALL_TYPES)
    bad_call_types = int((~valid_mask).sum())
    if bad_call_types:
        print(f"Warning: dropped {bad_call_types} row(s) with invalid call_type")
        df = df[valid_mask]
        call_type = call_type[valid_mask]

    df = df.copy()
    df["call_type"] = call_type.astype(int)

    return df.reset_index(drop=True)
