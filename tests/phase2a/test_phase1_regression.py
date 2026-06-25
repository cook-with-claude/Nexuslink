"""Phase 1 regression guard.

Runs the Phase 1 validation harness as a subprocess against freshly-regenerated
synthetic data.  The suite must exit 0 and report 100% pass — if it doesn't,
Phase 2A work has somehow disturbed the frozen Phase 1 algorithm.
"""

from __future__ import annotations

import subprocess
import sys
import pathlib

HERE = pathlib.Path(__file__).resolve().parents[2]
PHASE1 = HERE / "phase1_cdr"


def test_phase1_harness_passes():
    """Regenerate fixtures, run the Phase 1 harness, assert 100% pass."""
    # Step 1: regenerate sample_data.csv + ground_truth.json (deterministic, fixed seed).
    regen = subprocess.run(
        [sys.executable, str(PHASE1 / "dev_fixtures.py")],
        cwd=str(PHASE1),
        capture_output=True,
        text=True,
    )
    assert regen.returncode == 0, (
        f"dev_fixtures.py exited {regen.returncode}\n"
        f"stdout: {regen.stdout}\nstderr: {regen.stderr}"
    )

    # Step 2: run the Phase 1 validation harness.
    result = subprocess.run(
        [sys.executable, "main.py", "sample_data.csv", "ground_truth.json"],
        cwd=str(PHASE1),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"Phase 1 harness exited {result.returncode} (expected 0)\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "passed (100%)" in result.stdout, (
        f"'passed (100%)' not found in Phase 1 output:\n{result.stdout}"
    )
