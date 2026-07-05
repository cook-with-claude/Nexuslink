# SDD Progress — Phase 3 · Increment 3.1 (migrate-on-login)

**Plan:** `docs/superpowers/plans/2026-07-05-phase3-3.1-migrate-on-login.md`
**Branch:** `claude/phase3-3.1-migrate-on-login` (base = `main` @ `4d942b6`)
**Interpreter:** `C:\Users\nadim\OneDrive\Desktop\la passion\.venv\Scripts\python.exe` (py3.11.9)
**Test gate:** `.venv\Scripts\python.exe -m pytest tests/phase2a tests/architecture phase1_cdr/tests` (baseline 187; expect 190 after Task 1)

Tasks:
- [x] Task 1: Wire migrate() into get_db() (+3 tests)
- [x] Task 2: Activate ADR 0002 + HANDOFF

When a task's review is clean, append: `Task N: complete (commits <base7>..<head7>, review clean)`.

Task 1: complete (commits 070ac38..f3d77d8, review clean). Wired migrations.migrate() into get_db() (try/except closes conn on failure); 3 tests (v0 auto-upgrade, no-op current, fail-closed too-new); 190 passed. Note for final review: production handling of an uncaught SchemaTooNewError from a route relies on the global 500 handler (out of 3.1 scope).

Task 2: complete (commits f3d77d8..f125182, review clean). ADR 0002 Activation section + HANDOFF top entry; docs-only, phase1 empty. Spec + doc quality both clean.

FINAL WHOLE-BRANCH REVIEW (opus, range 4d942b6..f125182): verdict **ready-to-merge**.
No Critical/Important. Two Minor, both DEFER (do not block):
1. Production 500 for SchemaTooNewError/SchemaMismatchError bubbling from a route relies on the
   global INTERNAL 500 handler — adequate & fail-closed for 3.1 (3.1 ships no new migration, so the
   raise paths are only reachable via manual DB tamper/downgrade; login fail-closed wrapper also
   _lock()s). Tie a friendly "DB from newer app version" message to the FIRST shipped migration (3.2+).
2. No direct test for SchemaMismatchError (drifted-v0) propagation or the close-on-raise leak guard
   (both traverse the same except path the too-new test already exercises). Optional.
STATUS: all tasks done+reviewed; branch ready for Codex review + Nadim merge. Suite 190 passed. Phase1 frozen.

POST-CODEX: added test_get_db_closes_connection_when_migrate_raises (close-on-raise leak guard,
Codex prioritized suggestion, Nadim requested). Suite 191 passed, ruff clean, phase1 empty. Codex CLEAR.
