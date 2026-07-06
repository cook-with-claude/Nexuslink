# SDD Progress — Phase 3 · Increment 3.2b-1 (server master key + bootstrap unlock)

**Plan:** `docs/superpowers/plans/2026-07-05-phase3-3.2b-1-server-key.md`
**Branch:** `claude/phase3-3.2b-1-server-key` (base/tip at start = `ba0786a`; docs-only above `main`)
**Interpreter:** `C:\Users\nadim\OneDrive\Desktop\la passion\.venv\Scripts\python.exe` (py3.11.9)
**Test gate:** `.venv\Scripts\python.exe -m pytest tests/phase2a tests/architecture phase1_cdr/tests`
  Baseline **195**. Expected deltas: T1 +6/7 → 201 · T3 +3 → 204 · T4 +2 → 206 · T6 +2 → 208.
**Lint:** `ruff check app tests main.py`. **Boundaries:** `lint-imports` (WSL/CI only — no grimp win_arm64 wheel).
**Effort:** ★★★★★ carve-out — Opus implementers on ALL tasks, heavy adversarial + Codex review. NOT build-cheap.

Tasks (green suite per commit):
- [x] Task 1: `app/infra/bootstrap.py` keyfile init/unlock + INFRA-leaf AST guard + gitignore/import-linter (+6/7)
- [x] Task 2: `bootstrap_key` fixture across all integration fixtures (inert until T4)
- [x] Task 3: fail-closed `503 LOCKED` gate + `/api/status.locked` (+3)  [bundled → 57aba3f]
- [x] Task 4: `account.py` drops the DB key (`auth.json` → `{username,bcrypt_hash,created_at}`, bcrypt-only) (+2)  [bundled → 57aba3f]
- [x] Task 5: `auth/routes.py` login establishes session WITHOUT unlock; logout does NOT lock server; rewrite 3 fail-closed tests  [bundled → 57aba3f; hardened → f2117d4]
- [x] Task 6: `main.py` startup unlock (env→getpass; serve locked on failure) (+2)  [→ 20d7fce]
- [ ] Task 7: docs (ADR 0003 pt2 + api/surface/README/HANDOFF)

When a task's review is clean, append: `Task N: complete (commits <base7>..<head7>, review clean)`.

Task 1: complete (commits de50af0..1eefb43, review clean — Opus reviewer: spec ✅ Approved; both security checks PASS — no raw key on disk (exact-set test bites); wrong/empty/corrupt passphrase → BootstrapError). Fix 1eefb43 closed a plan-mandated Minor: non-string keyfile field values now map to BootstrapError (regression test bites: RED `AttributeError: 'int' object has no attribute 'encode'` → GREEN). **CURRENT BASELINE = 203 passed / 1 skipped** (plan's "201" is stale by +2: arch guard was in T1's count + the fix regression test). Task 2 adds NO tests → must STAY at 203/1.
ACCEPTED MINORS (final-review triage): (#2) `keyfile_path()` lacks `-> pathlib.Path` annotation — LEFT (adding `import pathlib` just for a cosmetic annotation is churn; pyright not a CI gate). (#3) redundant `path.parent.mkdir` in `_write_keyfile` — harmless, LEFT.

Task 2: complete (commit 1eefb43..5515a76, review clean — Sonnet reviewer: spec ✅ Approved, no Critical/Important). Pure inert fixture wiring: conftest `bootstrap_key` fixture + every enumerated integration fixture gets `DB_KEY=bootstrap_key`; `test_migrate_on_login` warm-up added; `/setup` still overwrites `DB_KEY` so genuinely inert. Verified no `TESTING` dropped, no assertion changed. Suite **203 passed / 1 skipped** unchanged. Minor (accepted): the brief's "(2 fixtures)" wording for test_export/test_spreadsheet was stale (each has 1 fixture + 1 no-DB requires_auth body) — doc nit in a one-shot brief, no action.

## CONTROLLER CARRY-FORWARD NOTES (do not lose across compaction)

**PLAN-ORDERING DEFECT + DECISION (2026-07-05):** Tasks 3 (lock gate), 4 (account drops key), 5 (routes decouple) are ONE atomic change and cannot each leave a green suite in the plan's order. The gate 503s when `DB_KEY is None`, but `routes._lock()` still nulls `DB_KEY` on logout/fail-closed until Task 5 — so gate-before-5 makes 13 tests 503 (8 test_auth logout-then-hit, 2 review_fixes, 3 transaction_semantics assert `DB_KEY is None`). The plan's own Task 4 is already transiently red pending Task 5. **DECISION: land 3+4+5 as ONE green commit** ("server-holds-key model"). The gate (Task 3) is already implemented UNCOMMITTED in the working tree (`__init__.py`, `guards.py`, `system.py`, `test_lock_gate.py`, `test_app.py`, `test_export.py`+`test_spreadsheet.py` requires_auth) and is verified correct vs the brief. Combined implementer adds Task 4 + Task 5 on top, gets full suite green, commits everything once. Then one heavy Opus review + adversarial security workflow on the combined diff. Tasks 6, 7 follow.
Combined-commit file set: `app/__init__.py app/api/guards.py app/api/system.py app/auth/account.py app/auth/routes.py tests/phase2a/{test_lock_gate.py,test_app.py,test_export.py,test_spreadsheet.py,test_account.py,test_transaction_semantics.py,test_auth.py}` **+ `tests/phase2a/test_review_fixes_branch3.py`** (added — I under-scoped it). Message: `feat(phase3-3.2b-1): server-holds-key model (lock gate + account/login decoupled from DB key)`. HARD gate = ZERO failures.

**SCOPE RESOLUTION for `test_review_fixes_branch3.py` (3 reds from the account key→None change; controller-authorized):**
- `test_create_account_init_failure_is_retryable` (line 36, "Fix #1") — REMOVE (obsolete by design: create_account no longer builds the DB / cleans stale `cdr.db`; the DB is built lazily by get_db/migrate, so the init-failure-retry scenario cannot occur). Also drop its now-inaccurate Fix-#1 comment header. NOTE this intentional behavior removal in ADR 0003 pt2 (Task 7).
- `test_connection_sets_busy_timeout` (line 67) + `test_delete_dataset_writes_audit_row` (line 222) — swap key source `account.create_account/authenticate` → `bootstrap_key` (`storage.connect(bootstrap_key)`); still-valid tests. Same sanctioned Task-5-Step-3 pattern.
- Post-fix expected: **206 passed, 1 skipped, 0 failed**.

account.py + routes.py verified CORRECT by controller (Pyright undefined-var warnings were STALE mid-edit noise; final account.py imports only hmac/json/logging/os/tempfile/datetime/config/crypto, no _b64e/storage/InvalidTag; ruff clean + green confirm). Combined-commit sanctioned work (Tasks 3+4+5) all green.

**Tasks 3+4+5 COMPLETE — commit `57aba3f` (206/1/0) + hardening `f2117d4`.** Adversarial security Workflow (4 Opus lenses + synthesis) over `5515a76..57aba3f`:
- **gate-bypass lens: CLEAN** (no /api subject-data route reachable while DB_KEY None; exempt set exact-match; before_request precedes login_required).
- **key-model lens: CLEAN** (DB_KEY bootstrap-only; no key on disk; auth.json shape exact). 1 minor = "no startup wires bootstrap→DB_KEY" — that's **Task 6**, correctly deferred.
- **fail-closed lens: 2 IMPORTANT (REAL) — FIXED in f2117d4.** The login + setup fail-closed tests were VACUOUS under TESTING (a propagated exception skips finalize/save_session, so the test passed whether or not login/setup called `_lock()` → a future removal of `_lock()` would leak an authenticated session undetected). Rewrote both to drive the PRODUCTION (non-TESTING) 500 path so `session.clear()` flushes → `GET==401` is load-bearing. **MUTATION-PROVEN:** with all 3 `_lock()` calls neutralized, all 3 fail-closed tests FAIL; restored → PASS.
- spec-tests lens + synthesis: hit session limit (didn't run). Controller covered the ground: removed `test_create_account_init_failure_is_retryable` is obsolete-by-design (verified); bootstrap_key swaps valid; no dead code (imports cleaned); no vacuous tests remain.
- **BEHAVIOR-CHANGE NOTE for Task 7 ADR + final review:** create_account no longer builds the DB (built lazily by get_db/migrate). Consequence: if the SETUP audit's lazy DB build fails, auth.json already exists → setup 409s on retry, but the account is recoverable via `/api/login` (login's `_audit` builds the DB). Acceptable/design-consistent; document in ADR 0003 pt2.

Task 7: complete (commit 20d7fce..bbacdfc, docs-only — reviewed WITHIN the final whole-branch review). ADR 0003 Part 2 + api.md + phase3-surface.md + README + HANDOFF. Suite unchanged 208/1.

## FINAL WHOLE-BRANCH REVIEW (Opus, range main..HEAD = 338d918..bbacdfc): **READY TO MERGE**
All 5 security properties PASS w/ evidence: gate-bypass (before_request precedes login_required; setup/login also gated; //api 308 edge not exploitable), fail-closed (production 500 path, load-bearing on _lock — f2117d4), key-model (only main.py:309 + __init__.py:28 default write DB_KEY; auth.json no key material), startup (BootstrapError+EOF+Ctrl-C caught, no passphrase logged), INFRA-leaf. Phase1 frozen; docs accurate. No Critical/Important. Minors all triaged KEEP: (1) keyfile_path annotation, (2) redundant mkdir (defensive, fine), (3) main.py E305 (ruff excludes E3), (4) setup-retryability change accurate+acceptable. NEW trivial: phase3-surface.md current_username() caller line numbers ~2 off (L88/L110 vs L90/L112) — doc-only, non-blocking, LEFT.

**BRANCH STATUS: ALL 7 TASKS DONE + REVIEWED. READY for Codex review + Nadim merge. NOT merged (Nadim merges).** Build commits: de50af0+1eefb43 (T1) · 5515a76 (T2) · 57aba3f (T3+4+5 bundled) · f2117d4 (fail-closed hardening) · 20d7fce (T6) · bbacdfc (T7 docs). Suite 208 passed / 1 skipped. Next increment: 3.2b-2 (users table).

Task 6: complete (commit f2117d4..20d7fce, review clean — Opus reviewer: spec ✅ Approved, no Critical/Important). `main.py` `resolve_and_unlock()` (env `LP_BOOTSTRAP_PASSPHRASE` → getpass; narrow `except BootstrapError` → None so server serves LOCKED, never crashes; no passphrase in logs; env→prompt precedence + EOF/Ctrl-C handled) + wired into `main()`. 2 non-vacuous tests (routed via the existing `entry`/importlib pattern to avoid `phase1_cdr/main.py` shadowing — sound). Suite **208 passed / 1 skipped**. ACCEPTED MINOR: E305 blank-line nit (ruff's default excludes E3; not a CI gate) — LEFT.


**Model policy:** implementers = Opus (★★★★★). Reviewers = Opus for T1,T3,T4,T5,T6; Sonnet for T2 (inert harness) + T7 (docs). Final whole-branch review = Opus. Then my adversarial security workflow, then Codex.

**Task 5 PLAN DEFECT — must deviate from the plan (confirmed against real code + errors.py):**
- The plan (T5 Step 2) says keep `assert GET /api/datasets == 401` for `test_audit_failure_during_logout_fails_closed` while changing DB_KEY assertion to `is not None`. **That assertion will FAIL under the new key model.** Reason: `_lock()` is now `session.clear()` ONLY (no `DB_KEY=None`). Under `TESTING=True` a propagated view exception skips response finalization, so `session.clear()` never flushes → the client cookie stays authenticated → `login_required` passes → GET returns 200, not 401. (DB_KEY used to be the crutch gate; it's gone now.)
- CORRECT FIX (Option A, verified vs `app/api/errors.py` which has a clean `@errorhandler(500)`): rewrite the logout test to drive the PRODUCTION non-propagating path so `session.clear()` actually flushes:
  ```python
  def test_audit_failure_during_logout_fails_closed(app_data_dir, bootstrap_key, monkeypatch):
      app = create_app()
      app.config.update(DB_KEY=bootstrap_key)   # NOT TESTING -> exception becomes 500, session flushes
      c = app.test_client()
      c.post("/api/setup", json={"username": "nadim", "password": "hunter2"})
      monkeypatch.setattr(audit_log, "write_audit", _boom)
      r = c.post("/api/logout")
      assert r.status_code == 500                       # audit failure surfaces as 500
      assert app.config["DB_KEY"] is not None           # server stays unlocked (master key process-wide)
      assert c.get("/api/datasets").status_code == 401  # THIS session was revoked -> fail-closed
  ```
  (Flask `handle_exception` → `_500` handler → `finalize_request` → `save_session` flushes the cleared session even though the view raised.)
- The **login** fail-closed test is fine AS LONG AS the implementer KEEPS the initial `client.post("/api/logout")` line (runs with real write_audit → clears+flushes session → stale cookie is unauthenticated → after failed login GET==401 holds). Do NOT drop that line.
- The **setup** fail-closed test is fine (fresh client, no prior flushed session → GET==401 holds); just flip its DB_KEY assertion to `is not None` per plan and add `bootstrap_key` + `DB_KEY=bootstrap_key`.

**TASK 3 EXTRA (beyond the plan text) — must fix or the lock gate breaks 2 tests:** the plan's Task 3 only unlocks `test_app.py`'s fixture. TWO MORE inline apps assert **401** with `DB_KEY=None` and will get **503** under the lock gate:
- `tests/phase2a/test_export.py:46` `test_export_requires_auth` (POST `/api/export/results.xlsx`)
- `tests/phase2a/test_spreadsheet.py:62` `test_records_requires_auth` (GET `/api/datasets/1/records`)
Fix both: add `bootstrap_key` param + `DB_KEY=bootstrap_key` to `config.update` (they then test unlocked-but-unauthenticated → 401, preserving intent — same pattern the plan uses for `test_app.py`).
VERIFIED SAFE/UNAFFECTED (no fix needed): `test_identity_context.py:27` (uses `test_request_context`, no `before_request` fires), `test_main.py` (only hits exempt `/api/health`), `test_ui.py` (non-`/api` paths only).

**Cross-checked & OK:** crypto sigs (`wrap_key→(nonce,ct)`, `unwrap_key(kek,nonce,ct)`), `config.DB_KEY_BYTES=32`/`SCRYPT_SALT_BYTES=16`, lock-gate placement (app before_request, `/api/` only, exempt health+status), `login_required` still ANDs authenticated+DB_KEY (belt-and-suspenders; unlocked server ⇒ reduces to session check — no change needed).
