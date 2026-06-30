"""The ONE door from the backend to the frozen Phase 1 algorithm.

`phase1_cdr/` is frozen and CI-validated; it is never edited and is reached only
through this module. The previously-duplicated `sys.path` dance (in validation.py
and detection_bridge.py) is consolidated here so there is a single owned seam.

Re-exports Phase 1's `detection` module plus the import-validation constants. All
backend code imports these from `app.infra.phase1`, never from `phase1_cdr/`
directly (enforced by the import-linter forbidden contract).
"""

from __future__ import annotations

import os
import sys

# app/infra/phase1.py -> repo root -> phase1_cdr
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_PHASE1 = os.path.join(_ROOT, "phase1_cdr")
if _PHASE1 not in sys.path:
    sys.path.insert(0, _PHASE1)

import detection  # noqa: E402
from loader import REQUIRED_COLUMNS, VALID_CALL_TYPES  # noqa: E402

__all__ = ["detection", "REQUIRED_COLUMNS", "VALID_CALL_TYPES"]
