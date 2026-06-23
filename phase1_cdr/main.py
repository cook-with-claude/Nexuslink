"""CLI entry point for Phase 1 validation.

Usage:
    python main.py <data_file> <ground_truth.json>

Loads a CDR file, runs every detector against the ground truth, prints a
pass/fail table plus a summary, and exits non-zero if anything failed.
"""

from __future__ import annotations

import json
import sys

import pandas as pd

from loader import CDRValidationError, load_cdr
from validate import validate, validate_contacts


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("Usage: python main.py <data_file> <ground_truth.json>")
        return 2

    data_file, ground_truth_file = argv[1], argv[2]

    try:
        df = load_cdr(data_file)
    except CDRValidationError as exc:
        print(f"Failed to load CDR data: {exc}")
        return 2

    with open(ground_truth_file, "r", encoding="utf-8") as fh:
        ground_truth = json.load(fh)

    rows = validate(df, ground_truth)
    contact_rows = validate_contacts(df, ground_truth)

    table = pd.DataFrame(rows, columns=[
        "user", "test", "expected", "detected", "confidence", "alternatives", "result",
    ])
    contact_table = pd.DataFrame(contact_rows, columns=[
        "user", "rank", "number", "total",
        "call_out", "call_in", "sms_out", "sms_in", "result",
    ])
    # Render the full tables without truncation.
    with pd.option_context(
        "display.max_rows", None,
        "display.max_colwidth", None,
        "display.width", None,
    ):
        print("=== Home / Work / Frequent locations ===")
        print(table.to_string(index=False))
        print("\n=== Frequent contacts (ranked, by communication type) ===")
        print(contact_table.to_string(index=False))

    all_rows = rows + contact_rows
    total = len(all_rows)
    passed = sum(1 for r in all_rows if r["result"] == "PASS")
    pct = (passed / total * 100) if total else 0.0
    print(f"\n{passed}/{total} passed ({pct:.0f}%)")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
