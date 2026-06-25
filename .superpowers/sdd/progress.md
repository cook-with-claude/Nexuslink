# SDD Progress — Phase 2A Backend Foundation

**Plan:** `docs/superpowers/plans/2026-06-24-phase2a-backend-foundation.md`
**Branch:** `claude/phase2a-design` (base = `main`)
**Status:** in progress — 13 of 14 done; **Task 14 PARTIAL (committed WIP, NOT reviewed)**.
**Resume at:** finish Task 14 (see the Task 14 WIP entry at the bottom), then the
final whole-branch review (Task 15 in the todo list).
**Branch tip at session close:** `9b19df5` (27→28 commits ahead of `main`).
**Full phase2a suite: 47 passed** (46 + the new regression guard). Phase 1
unit suite expected 18. `git diff --stat main -- phase1_cdr/` is EMPTY (frozen).
**Interpreter for all tasks:** `C:\Users\nadim\OneDrive\Desktop\la passion\.venv\Scripts\python.exe` (Python 3.11.9 ARM64). `phase1_cdr/.venv` is DLL-blocked — do not use it. `cryptography==46.0.3` (49.x fails ARM64 build); APIs compatible.

Branch tip before any task code: `f252f1e`. Anything in `git log` past `f252f1e`
is completed task work; reconcile against the checkboxes below after a resume.

**FROZEN-PHASE1 BASELINE CORRECTION (found during Task 8):** The plan/memory say
"phase1_cdr must stay byte-identical to tag `v1.0-phase1`" — that is WRONG. The
v1.0-phase1 tag predates the 9-column frequency feature (tag = 6 cols; `main`/this
branch = 9 cols). The real frozen baseline is **`main`** (the branch base).
Verified `git diff --stat main -- phase1_cdr/` is EMPTY through Task 8 — branch has
not touched phase1. **TASK 14 FIX:** its Step 4 verification must diff against
`main` (or `git merge-base main HEAD`), NOT `v1.0-phase1`, or it will falsely report
the 6→9 column frequency diff and fail.

- [x] Task 1: Dependencies, config, gitignore
- [x] Task 2: Crypto primitives (crypto.py)
- [x] Task 3: SQLCipher storage + schema + on-disk encryption proof
- [x] Task 4: Account lifecycle (account.py)
- [x] Task 5: Audit log writer (audit.py)
- [x] Task 6: App factory, sessions, public routes, get_db, error envelope
- [x] Task 7: Auth blueprint (setup/login/logout/change-password)
- [x] Task 8: CDR row validation (validation.py)
- [x] Task 9: Import pipeline + datasets endpoints
- [x] Task 10: Targets blueprint
- [x] Task 11: Detection bridge (only seam to phase1)
- [x] Task 12: Analysis blueprint
- [x] Task 13: Desktop entry point (main.py)
- [ ] Task 14: Full-suite gate — Phase 2A + Phase 1 regression

When a task's review comes back clean, append:
`Task N: complete (commits <base7>..<head7>, review clean)`

---

Task 1: complete (commits dc3e6fb..7833518, review clean). SQLCipher hard gate
PASSED — `sqlcipher ok 3.51.1`, flask/bcrypt/cryptography/webview all import on
the root `.venv`. Reviewer Approved. Follow-up commit dropped an unused import
and added `testpaths = tests`. Minor (deferred to final review): `requirements.txt`
leaves `sqlcipher3-wheels` unpinned (install-time risk on other machines).

Task 2: complete (commits 7833518..8bfb04b, review clean). bcrypt/scrypt-KEK/
AES-GCM verbatim from plan; reviewer Approved. Follow-up hoisted `import os` to
module top and added key(32)/nonce(12) length asserts. Minor (deferred to final
review): `verify_password` could wrap `bcrypt.checkpw` in `bool()` for annotation
strictness across older bcrypt versions (harmless on installed version).

Task 3: complete (commits 7995b8c..9f1e8a8, review clean). SQLCipher storage,
5-table schema, on-disk encryption proof all pass (SQLCipher 3.51.1; executescript
does NOT reset foreign_keys). Reviewer Approved. Follow-up: row_factory now set
AFTER PRAGMA key (invariant clarity), added `-> sqlcipher.Connection` annotation,
narrowed FK test to concrete `IntegrityError`. No deferred minors.

Task 4: complete (commits 7b5942d..afba52a, review clean after fixes). Envelope
key mgmt (random db_key, scrypt KEK, AES-GCM wrap, bcrypt verifier); auth.json
sidecar; create/authenticate/change_password. Reviewer found 2 plan-mandated
Important findings — Nadim approved both fixes: (1) authenticate now constant-time
(always runs bcrypt + hmac.compare_digest, removed username-enumeration timing
oracle); (2) change_password guards no-account → AuthError (was raw FileNotFoundError).
7 tests pass. Minor deferred to final review: _save not atomic (temp+rename would
harden); InvalidTag defence branch untested (a tamper test would lock it).

Task 5: complete (commit cdf86d6, review clean). audit.write_audit + 9 event-type
constants; parameterized INSERT, UTC ISO ts, NULL detail when None. Reviewer
Approved, no Critical/Important. Minor deferred to final review: two brief-mandated
test assertions are weak (`"foo" in detail` substring; `row["ts"]` truthy-only —
could use `datetime.fromisoformat`).

Task 6: complete (commits 442b183..746ea5f, review clean). create_app factory,
ok/err JSON envelope, per-request get_db on flask.g + teardown close, login_required
(session flag + DB_KEY dual-check), HttpOnly/SameSite=Strict cookies, per-launch
SECRET_KEY, health/status public routes, 404/405/500 JSON handlers. Four blueprint
registrations COMMENTED OUT (lines ~90-97) — uncomment as Tasks 7/9/10/12 land.
Reviewer Approved; follow-up dropped unused `config` import. Minor deferred to final
review: login_required content-length guard skips chunked POSTs (light-CSRF only);
no direct 401 test here (covered by Task 7's test_protected_route_requires_login).

Task 7: complete (commits 7c64372..7a86a9f, review clean after fixes). Auth
blueprint setup/login/logout/change-password; buffered LOGIN_FAIL (stashed in
PENDING_FAILS, flushed on next successful unlock); session unlock/clear; auth
blueprint uncommented. Reviewer found one Important deviation — implementer had
turned the Task-6 `_404` handler into a global auth-wall (unknown route → 401 when
logged out) to satisfy a MIS-SEQUENCED plan test (`test_protected_route_requires_login`
asserted 401 on /api/targets, which doesn't exist until Task 10). Nadim chose:
revert the wall to plain 404, retarget the test to `POST /api/logout` (a protected
route that exists now), drop unused `storage` import. 8 tests pass. NOTE for Task 10:
the /api/targets-specific 401 case is NOT re-added — Task 10's own tests cover targets
auth. Minor deferred to final review: login success path does N+1 audit commits
(could group flush loop into one commit); PENDING_FAILS lost on process restart (by design).

Task 8: complete (commits b66834e..d837ab2, review clean). validation.missing_columns
+ validate_row, reusing phase1 loader REQUIRED_COLUMNS (9 cols) + VALID_CALL_TYPES
read-only via sys.path shim (no phase1 edit; verified `git diff main -- phase1_cdr/`
empty). Reviewer Approved; follow-up added the two interface type annotations and a
missing-required-field skip test (now 6 tests). Pyright to_datetime/int(float) None
warnings confirmed NOT real runtime risks (errors="coerce" + try/except guard them).

Task 9: complete (commits 352f3a7..f4a3c95, review clean). imports blueprint:
POST /api/imports (multipart xlsx → validate → parameterized executemany bulk
insert), GET /api/datasets, GET phone-numbers, DELETE dataset (ON DELETE CASCADE).
sample_xlsx fixture converts phase1 sample_data.csv → xlsx in tmp_path (no phase1
edit). Only imports_bp uncommented. Reviewer Approved; follow-up strengthened
test_delete_dataset_cascades to assert phone-numbers 404 after delete (real cascade
proof) + hoisted conftest pandas import. DISMISSED reviewer's audit-atomicity concern:
get_db teardown closes WITHOUT commit, so if audit write raises the whole txn rolls
back (caller gets 500, no partial persist) — atomic, not a defect.

Task 10: complete (commits f9e3818..577a71a, review clean). targets blueprint
POST/GET/DELETE; UNIQUE(dataset_id, phone_number) → 409 on dup even with different
name (test proves pair-keyed not name-keyed); two distinct 404s (no dataset / phone
not in dataset); parameterized SQL; TARGET_CREATE/DELETE audited. Only targets_bp
uncommented. Reviewer Approved; follow-up added DELETE-unknown-id 404 test (now 4).
Deferred to final review: app-level dup pre-check not race-safe (raw IntegrityError
possible under concurrent writes) — spec classifies acceptable for single-user; a
try/except IntegrityError→409 around INSERT would make it bulletproof. Minor: POST
omits created_at (GET includes it); phone_number falsy-check accepts int 0.

Task 11: complete (commits bb40654..35d9af1, review clean). detection_bridge —
THE only seam to phase1 (read-only import, phase1 untouched vs main). rows_to_frame
(9-col, datetime ts, int call_type/duration) + analyze_frame (all 5 detectors,
full gate-trace serialization). EQUIVALENCE test passes: bridge home/work/contacts
== direct detection.* calls on real phase1 sample. Reviewer Approved; follow-up
added `.fillna(0)` guard on call_type cast (crash-proofs an all-null batch; never
fires on validated DB data) + a work-equivalence assertion. All Pyright .astype/
.fillna/to_dict warnings = pandas stub limits, not runtime risks (equivalence proves it).

Task 12: complete (commit b2eed15, review clean — no Critical/Important). analysis
blueprint POST analyze + GET result; dual-column CDR filter (dataset_id AND
phone_number); pre-work 404; parameterized INSERT/SELECT; ANALYSIS audited; safe
?top_n= parse; round-trip persistence. analysis_bp uncommented → ALL 4 BLUEPRINTS
ACTIVE. End-to-end test: User A (01000001) → home "Hamra", confidence "High", gates
{N,share,closeness,density}, persisted+retrievable. **FULL phase2a suite = 45 passed.**
Minor (dismissed as safe): top_n=0/neg won't 500 (phase1 uses [:top_n] slicing);
frequent_contacts shape already locked by Task 11 bridge tests.

Task 13: complete (commit e9b3b6a, review clean — no actionable Critical/Important).
main.py (repo root): start_server (werkzeug make_server, ephemeral port, daemon
thread, returns OS-assigned server_port), wait_until_ready (polls /api/health,
raises on timeout), main() (PyWebView window, `import webview` inside main, pragma
no-cover). Host 127.0.0.1 only. Test starts a real server + polls health + shuts
down in finally → 1 passed. GUI smoke test (python main.py) deferred to a human with
a display. NOTE: window opens at /api/health — CORRECT for Phase 2A (backend-only,
no frontend route yet); revisit when a UI phase adds `/`. Minor deferred to final
review: wait_until_ready sleeps only in except branch (never fires for this server);
test doesn't assert thread.is_alive() False after join.

Task 14: **PARTIAL — committed WIP at `9b19df5`, NOT reviewed.** Done so far:
(1) `tests/phase2a/test_phase1_regression.py` — regenerates phase1 fixtures + runs
the phase1 harness as a subprocess, asserts exit 0 + 100% (passing, it's the 47th
phase2a test); (2) `tests/phase2a/test_main.py` hardened — loads root `main.py` via
`importlib.util.spec_from_file_location` instead of `import main`, so the full-suite
run can't shadow it with `phase1_cdr/main.py` (test_bridge.py adds phase1_cdr to
sys.path). **STILL TODO to finish Task 14:**
  a. Add the Phase 2A section to root `README.md` (Flask+PyWebView backend,
     SQLCipher, run cmds: `pytest tests/phase2a` + `python main.py`, link the spec).
  b. Run + record BOTH suites: `.venv\Scripts\python.exe -m pytest tests/phase2a`
     (expect 47) and `.venv\Scripts\python.exe -m pytest phase1_cdr/tests` (expect 18).
  c. Verify frozen phase1: `git diff --stat main -- phase1_cdr/` → MUST be EMPTY.
     **Use `main`, NOT the `v1.0-phase1` tag** (tag predates the 9-col frequency
     feature — see baseline-correction note above).
  d. Confirm `git status` clean after the regression test regenerates phase1
     sample_data.csv/ground_truth.json (deterministic; must be byte-identical).
  e. Commit README + mark Task 14 done.
  f. Then run the Task 14 REVIEW gate (it was never run — the WIP is unreviewed),
     covering the two new test files at `9b19df5`.

INTERPRETER for everything: `C:\Users\nadim\OneDrive\Desktop\la passion\.venv\Scripts\python.exe`
(Python 3.11.9 ARM64). NEVER use `phase1_cdr/.venv` (DLL-blocked). cryptography==46.0.3.

DEFERRED-MINOR LIST for the final whole-branch review (Task 15) to triage:
- T1: requirements.txt leaves sqlcipher3-wheels unpinned (other-machine install risk).
- T2: verify_password could wrap bcrypt.checkpw in bool() for annotation strictness.
- T4: account _save not atomic (temp+rename would harden); InvalidTag defence branch
  untested (a tamper test would lock it).
- T5: two brief-mandated audit-test assertions are weak ("foo" in detail substring;
  row["ts"] truthy-only — could use datetime.fromisoformat).
- T6: login_required content-length guard skips chunked POSTs (light-CSRF only).
- T7: login success path does N+1 audit commits (could group flush into one commit);
  PENDING_FAILS lost on process restart (by design).
- T10: app-level dup pre-check not race-safe (raw IntegrityError possible under
  concurrent writes) — spec says acceptable for single-user; try/except
  IntegrityError→409 around INSERT would make it bulletproof. POST omits created_at
  (GET includes it); phone_number falsy-check accepts int 0.
- T13: wait_until_ready sleeps only in except branch (never fires for this server);
  test_main doesn't assert thread.is_alive() False after join.
- T13 (design, NOT a bug): main() opens the window at /api/health — correct for
  backend-only Phase 2A; revisit when a UI phase adds a `/` route.

DESIGN DECISIONS Nadim made during reviews (do NOT re-litigate):
- T4: hardened authenticate to constant-time (always run bcrypt + hmac.compare_digest)
  + change_password no-account guard → AuthError. APPROVED & DONE.
- T7: reverted the implementer's `_404` auth-wall back to plain 404; retargeted the
  mis-sequenced `test_protected_route_requires_login` to `POST /api/logout`. APPROVED
  & DONE. (The plan's original test asserted 401 on /api/targets, which doesn't exist
  until Task 10 — do NOT re-add that assertion.)
