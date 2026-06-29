# Codex review fixes

Reviewed `origin/claude/ui-ux-redesign` at `d5e4617` against `main` at `039a0ef`.

## Change made

- Fixed `navigableRows()` so row-level Enter/Space/Arrow handling only runs when the table row itself has focus. This prevents nested action buttons, such as dataset delete, from also triggering row navigation during keyboard activation.

## Verification

- `.venv\Scripts\python.exe -m pytest tests\phase2a\test_ui.py` - 8 passed.
- `.venv\Scripts\python.exe -m pytest tests\phase2a` - 99 passed.
