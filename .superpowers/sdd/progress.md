# SDD Progress — Phase 3 · Increment 3.2a (identity de-globalization)

**Plan:** `docs/superpowers/plans/2026-07-05-phase3-3.2a-identity-deglobalization.md`
**Branch:** `claude/phase3-3.2a-identity-deglobalization` (base = `main` @ `a17c4c2`; plan commit `048d605`)
**Interpreter:** `C:\Users\nadim\OneDrive\Desktop\la passion\.venv\Scripts\python.exe` (py3.11.9)
**Test gate:** `.venv\Scripts\python.exe -m pytest tests/phase2a tests/architecture phase1_cdr/tests` (baseline 191; expect 195 after Task 2)

Tasks:
- [x] Task 1: identity module + accessor/writer swap (+3 tests)
- [x] Task 2: data-free boundary guard (AST + import-linter tier) (+1 test)
- [x] Task 3: ADR 0003 part 1 + HANDOFF

When a task's review is clean, append: `Task N: complete (commits <base7>..<head7>, review clean)`.

Task 2: complete (commit c183ed9..5642dff, review clean — spec ✅, quality Approved, zero findings).
- `tests/architecture/test_boundaries.py` +`test_identity_context_is_data_free` (AST: no SQL, no `app.*` import — genuinely bites); `pyproject.toml` layers contract gains `app.api.identity` at the SUPPORT tier (independence contract untouched). identity.py bite-check reverted (not in commit). Controller re-ran gate: 195 passed, phase1 frozen.
- Note: Task 2 subagent hit an account rate-limit during its RETURN phase AFTER committing 5642dff; `.superpowers/sdd/task-2-report.md` is stale (leftover 3.1 content) — cosmetic only, commit verified via diff + git show + suite run.

Task 3: complete (commit 5642dff..0426896, review clean — spec ✅, quality Approved).
- New `docs/adr/0003-server-key-and-identity.md` (accepted, part 1; part 2 = 3.2b appends). HANDOFF top entry above the 3.1 entry. Docs-only, phase1 frozen, 195 passed. Ledger left out of commit (correct).

ACCUMULATED MINORS for final-review triage:
1. `clear_identity()` reached only from its unit test (matches brief design; 3.2b groundwork) — likely leave.
2. `current_username() -> str | None` now propagates to `_audit(username: str)`; pyright flags it (NOT a CI gate; ruff/import-linter/pytest are). Runtime-safe — audit accepts None actor by design. Pre-existing in spirit.
3. HANDOFF 3.2a entry says the "three config[USERNAME] fail-closed assertions ... re-pointed at the session identity" — but Task 1 re-pointed only 2; the audit-failure LOGOUT case keeps the DB_KEY+401 gate with an explanatory comment (a session assertion can't hold: Flask discards session mutations when the view raises under TESTING). One-line HANDOFF accuracy tweak worth making before Codex handoff.

FINAL WHOLE-BRANCH REVIEW (opus, range a17c4c2..0426896): verdict **READY-TO-MERGE**. No new findings (Critical/Important/Minor). Auth gate verified intact (login_required still gates on authenticated + DB_KEY; DB_KEY confirmed process-global, never in session; no cross-client leak / logout-survival / bypass). Triage: minor 1 leave (intentional), minor 2 defer to 3.2b (authz signature reshape; runtime-safe, pyright not a CI gate), minor 3 = fix the HANDOFF wording (done) — the logout test deviation itself confirmed SOUND, no fail-closed gap.

POST-FINAL fix: HANDOFF wording corrected in commit 7599ad2 (docs-only). Branch tip = 7599ad2.
STATUS: all 3 tasks done+reviewed; final review READY-TO-MERGE; branch ready for Codex review + Nadim merge. Suite 195 passed, phase1 frozen. NOT merged (Nadim merges).

Task 1: complete (commits 048d605..c183ed9, review clean — spec ✅, quality Approved).
- New leaf SUPPORT module `app/api/identity.py` (flask-only); `current_username()` delegates; `_unlock`/`_lock` write/clear session identity; `USERNAME` config default removed; `DB_KEY` retained. 194 passed.
- DEVIATION (accepted, reviewer-confirmed correct): brief Step 9's `session_transaction()` sub-assertion in `test_audit_failure_during_logout_fails_closed` was replaced with a comment — under TESTING Flask discards a session mutation when the view raises, so `_lock()`'s `session.clear()` runs (DB_KEY→None) but never flushes to the cookie. The real fail-closed gate (DB_KEY + 401) is still asserted. Not a no-op test.
- Important finding from reviewer = the import-linter/AST enforcement of the identity leaf invariant → THIS IS TASK 2's deliverable (reviewer was task-scoped). No fix needed.
- Minor: `clear_identity()` reached only from its unit test (matches brief design; 3.2b groundwork).
- Note for final review: `current_username() -> str | None` now propagates an explicit optional to `_audit(username: str)`; pyright (not a CI gate) flags it. Runtime-safe (audit accepts None actor by design). Pre-existing in spirit; not fixed here.
