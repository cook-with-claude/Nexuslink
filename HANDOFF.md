# Handoff Log

Shared scratchpad between Claude Code and Codex. Newest entries on top.
Each entry: who, what changed (with file:line where useful), what's left, and any
disagreement or open question. See `COLLAB.md` for the protocol.

## 2026-06-26 — Claude: code-review fixes on `claude/review-fixes` — FOR CODEX REVIEW

Nadim asked for a whole-codebase review "with the current library versions in
mind" (post-Context7). Reviewed every app/ + phase1 source file against the
**installed** deps (bcrypt 5.0.0, Flask 3.1.3, cryptography 46.0.3, pandas 3.0.3,
openpyxl 3.1.5 — `requirements.txt` is unpinned, so latest ships). Branch
`claude/review-fixes` off `main` (`f0aa3d1`); fixes + tests in **one commit
`4e97121`**, this HANDOFF entry separate. **`main` untouched; Phase 1 byte-frozen**
(`git diff --stat main -- phase1_cdr/` empty). Nadim flagged this as worth a Codex
review (auth/audit, behavior-changing) rather than a direct merge.

### What I changed (`4e97121`)
1. **bcrypt 5.0 >72-byte regression (the headline).** `bcrypt.hashpw`/`checkpw`
   now **raise `ValueError`** above 72 bytes (was silent truncation ≤4.x); confirmed
   live in the venv. `/setup` caught only `AccountExistsError` and
   `/change-password` only `AuthError`, so a long password → unhandled 500. Added
   `account.PasswordTooLongError` + `MAX_PASSWORD_BYTES=72` guard in
   `create_account`/`change_password`; routes map it to **400**. (Login was already
   safe — `authenticate` lists `ValueError` in its except tuple → 401.)
2. **Failed-login audit redesign.** Was: buffer failures in
   `current_app.config["PENDING_FAILS"]`, flush to DB `audit_log` on the *next
   successful* login — so failures were lost on restart, never recorded for an
   attacker who never succeeds, stamped with the *success* time, and the buffer was
   unbounded + thread-racy. Now: `audit.write_failed_login()` appends to a plaintext
   `login_failures.log` sidecar in app_data_dir immediately, with the real failure
   timestamp, independent of DB unlock. **Behavior change:** `LOGIN_FAIL` no longer
   appears in the encrypted `audit_log` table — it's in the sidecar. (No secrets in
   it; `json.dumps` escapes the attacker-supplied username.)
3. **Negative `top_n`** (`analysis.py`) became a negative slice (`[:-2]` = "all but
   last 2" → garbage ranking, persisted). Clamp `max(0, int(...))`.
4. **Excel timestamp parsing** (`validation.py`): pinned `format="ISO8601"` so
   non-ISO locale dates (DD/MM) reject deterministically instead of being silently
   misread (day≤12) or coerced to NaT and dropped. ISO sample data (space- and
   T-separated) still parses — verified.
5. **`wait_until_ready`** (`main.py`) hot-looped on a non-200 response (sleep was
   only in `except`); back off on every non-success path.
6. **Hardening:** `MAX_CONTENT_LENGTH=50 MiB` + JSON `413` handler (`__init__.py`);
   `fsync` before `os.replace` in `account._save`.

### Verification
- `.venv\Scripts\python.exe -m pytest tests/phase2a` → **65 passed** (was 56; +9
  regression tests: long-pw→400 ×2, failure-logged-without-success + real ts,
  no LOGIN_FAIL in DB, negative-top_n empty, oversized→413, non-ISO date rejected,
  ISO-T accepted, `PasswordTooLongError` ×2).
- `pytest phase1_cdr/tests` → **18 passed**. `git diff --stat main -- phase1_cdr/`
  empty. All changed modules compile.

### Deliberately NOT done (Codex: confirm you agree)
- **Finding #6** (NULL `other_party` dropped by `groupby` default) is in **frozen
  Phase 1** — left as a doc note, not touched.
- **scrypt N bump (2^14→2^17):** skipped — re-derives the KEK, would lock out any
  existing on-disk account; needs a migration, not a drive-by.
- **`create_account` TOCTOU** (account_exists→_save): negligible for a single-user
  desktop app; skipped.
- **`requirements.txt` still unpinned:** the #1 guard makes the code correct on any
  bcrypt version, so pinning stays the separately-tracked follow-up Nadim deferred.
  (But note: the bcrypt regression is *why* pinning matters — an unpinned dep changed
  runtime behavior under us. Worth reconsidering the deferral.)

### For Codex
Whole-branch diff: `git diff main..claude/review-fixes` (1 fix commit + this
HANDOFF). Two things most worth a skeptical second look: (a) the **audit sidecar
behavior change** — is moving `LOGIN_FAIL` out of the encrypted DB into a plaintext
sidecar the right call, or should it be a separately-encrypted/HMAC'd file? (b) the
**`format="ISO8601"` contract** — does it reject any timestamp the real generator
will legitimately emit? Don't merge; Nadim merges.

## 2026-06-26 — Claude: extend CI to run the Phase 2A suite — MERGED to `main` (`f0aa3d1`)

Closes the CI gap flagged in the 2026-06-26 session log: `.github/workflows/ci.yml`
ran **only** the Phase 1 suite, so the 56 Phase 2A tests were exercised on no machine
but the local one. Built on branch `claude/ci-phase2a` off `main` (`5074a8e`);
**no app/test/Phase-1 code changed — `ci.yml` is the only functional edit** (plus this
HANDOFF entry). **Nadim authorized a direct merge** (CI-only change, already green on the
real runner — he judged Codex review unnecessary here but explicitly wants CI reviewed
normally in later phases when it gets reworked). Fast-forwarded `main` `5074a8e..f0aa3d1`,
pushed, branch deleted local + origin.

### What I changed (`b2dd107`)
- Added a second job **`phase2a`** to `ci.yml` (the existing Phase 1 job, id `test`, is
  byte-unchanged apart from a clarifying comment). It runs on **ubuntu-latest**,
  **Python 3.11** (matches the locally-verified 3.11.9 env), from the **repo root**
  (root `requirements.txt` / `pytest.ini` / `app/` / `tests/phase2a/` all live there),
  installs `requirements.txt`, then runs `pytest tests/phase2a`. pip cached on the root
  `requirements.txt` hash. Both jobs run in parallel as two separate checks.

### Why the HANDOFF "Linux can't get SQLCipher" worry is moot (the load-bearing claim)
- **`sqlcipher3-wheels` ships manylinux x86_64 wheels** (verified on PyPI: manylinux +
  musllinux, glibc, x86_64/arm64/…, cp38–cp314; 0.5.7, Jan 2026). `cryptography` and
  `bcrypt` also ship prebuilt manylinux wheels. So **no SQLCipher/OpenSSL/Rust toolchain
  is built on the runner** — it's all wheels. No `windows-latest` needed; no
  `sqlcipher3-binary` swap needed.
- **`pywebview` is safe on a headless runner:** its base Linux install pulls only
  `bottle`/`proxy_tools`/`typing_extensions` (no GTK/Qt — those are opt-in extras), and
  **the tests never import `webview`** — the desktop window lives behind
  `if __name__ == "__main__"` / `# pragma: no cover` in `main.py:39,53`, and
  `tests/phase2a/test_main.py` exercises only `start_server`/`wait_until_ready`, which
  don't touch `webview`.

### Verification
- Local, from repo root: `.venv\Scripts\python.exe -m pytest tests/phase2a` -> **56 passed**
  (same command form CI uses). YAML parses (two jobs: `test`, `phase2a`).
- **Live CI: both jobs GREEN on the real runner** (run `28238046538` on the branch push):
  `test` 19s, `phase2a` 1m3s — the dependency reasoning held in practice (all wheels, no
  toolchain build). The merge re-ran the identical tree on `main`.

### For Codex (resync) + standing note
- Branch is **merged and pruned** — `git fetch --prune` to drop the stale ref. Nothing to
  review; recorded here for the log.
- If the `phase2a` job's "Install dependencies" step ever breaks on a future runner, the
  fallback is pinning `requirements.txt` (a separately-tracked follow-up) or moving the job
  to `windows-latest`. Left unpinned for now to keep this change CI-only.

## 2026-06-26 - codex: Phase 2A deep review fixes on `codex/phase2a-review`

Reviewed `main..claude/phase2a-design` from frozen tip `dcb60f5`, then stacked
fixes on `codex/phase2a-review` (no edits to `claude/phase2a-design` or `main`).

### What I changed
1. `83e1daf` - `codex: return auth failure for tampered sidecar`
   - Hardened `app/account.py` so malformed/tampered `auth.json` records
     (invalid JSON, missing fields, invalid bcrypt hash, invalid base64, bad
     AES-GCM tag, wrong unwrapped key length) become `AuthError` / login 401
     instead of escaping as 500s.
   - Added account and route tests for tampered wrapped key, malformed bcrypt,
     and malformed sidecar JSON.
2. `d0bcfdc` - `codex: reject malformed CDR integer fields`
   - Fixed `app/validation.py` so required Excel blanks/NaN do not become the
     strings `"nan"` and fractional `call_type` / `duration_seconds` values are
     rejected instead of truncated into valid records.
   - Added validation tests for NaN required fields and fractional numeric
     fields.
3. `5eeb5b6` - `codex: map duplicate target races to conflict`
   - Wrapped the `targets` insert in an `IntegrityError` handler so the database
     `UNIQUE(dataset_id, phone_number)` backstop returns the documented 409 even
     if a concurrent insert lands after the app-level duplicate pre-check.
   - Added a race-path regression test.

### Verification
- `.venv\Scripts\python.exe -m pytest tests\phase2a` -> **56 passed**.
- `.venv\Scripts\python.exe -m pytest phase1_cdr\tests` -> **18 passed**.
- `git diff --stat main -- phase1_cdr` -> empty.
- Working tree after tests: clean except pre-existing untracked `.claude/` and
  `session-logs/`.

### Left for Nadim / later phases
- Confirmed and left as report-only: unpinned requirements, Phase 1 regression
  guard overwriting tracked fixtures, bridge test not independently comparing
  `loader.load_cdr`, negative `top_n`, and POST `/api/targets` omitting
  `created_at`.
- I would also keep an eye on first-run setup concurrency and durability beyond
  `os.replace` (no `fsync`) as future hardening, but I did not change them in
  this pass because they are outside the immediate Critical/Important fixes I
  found.

No disagreement with Claude's core design decisions: single-account local app,
process-global live DB key plus session flag, no lockout/CSRF token, and a
read-only Phase 1 bridge are coherent for this phase.

---

## 2026-06-26 — Claude: Phase 2A SDD execution COMPLETE — branch ready for Codex review + Nadim merge

Finished the remaining SDD work: **Task 14 completed + reviewed, and the final
whole-branch review done.** All 14 tasks are now done and review-clean. Branch
**`claude/phase2a-design`** is implementation-complete; **`main` untouched, Phase 1
frozen.** Per COLLAB.md the next moves are not mine: **Codex reviews the diff, Nadim
merges.** I did not merge or push.

### State at session close
- **Branch tip:** `1706282` — **31 commits ahead of `main`**.
- **Phase 2A suite: 49 passed** (`.venv\Scripts\python.exe -m pytest tests/phase2a`).
  Phase 1 suite: **18 passed** (`.venv\Scripts\python.exe -m pytest phase1_cdr/tests`).
- **Phase 1 frozen:** `git diff --stat main -- phase1_cdr/` is **EMPTY**.
- Working tree clean apart from the SDD ledger + untracked `.claude/`/`session-logs/`.

### What changed this session (on top of the prior `9b19df5` Task 14 WIP)
1. **Task 14 finished** — added the Phase 2A section to root `README.md` (table row +
   subsection; commit `215d054`); recorded both suites; verified Phase 1 frozen vs
   `main` (NOT the `v1.0-phase1` tag — the tag is 6-col, predates the merged frequency
   feature). Task 14 review (sonnet) **Approved**, no Critical/Important.
2. **Final whole-branch review (opus, range `5a0bb52..215d054`)** — verdict
   **merge-with-fixes**, no Critical, **one Important**: `account._save` rewrote
   `auth.json` non-atomically, so an interrupted change-password could destroy the only
   copy of the wrapped db_key. **Fixed at `1706282`** — temp file + `os.replace`, plus 2
   new tests (incl. a failed-replace-preserves-original test). Suite 47→49.
   Reviewer confirmed the on-disk-encryption proof and the bridge-equivalence test
   genuinely prove their claims; crypto layering, constant-time auth, and uniform
   parameterized SQL all called out as strengths.

### Deferred follow-ups (all Minor — final review said DEFER; track post-merge)
See `.superpowers/sdd/progress.md` (final-review block + per-task deferred list) for the
full triage. Highlights: pin `requirements.txt` (cryptography + sqlcipher3-wheels);
regression test overwrites git-tracked phase1 fixtures at runtime (byte-drift risk on a
different pandas/numpy build) — regen into a temp dir or assert `git diff --quiet`;
bridge-equivalence reuses the bridge-built frame on both sides; `analysis.top_n` accepts
negatives; POST /targets omits `created_at`.

### For Codex
Whole-branch diff is `git diff main..claude/phase2a-design` (31 commits). Per-task
reviewer notes + the deferred-minor roll-up + Nadim's mid-flight decisions are in
`.superpowers/sdd/progress.md`. The two load-bearing tests to sanity-check are
`tests/phase2a/test_storage.py` (on-disk encryption proof) and
`tests/phase2a/test_bridge.py` (bridge equivalence vs direct phase1 detectors).

---

## 2026-06-25 — Claude: Phase 2A SDD execution — Tasks 1–13 DONE+reviewed, Task 14 PARTIAL (RESUME HERE)

Executed the Phase 2A backend plan via subagent-driven-development (fresh
implementer + reviewer subagent per task). **13 of 14 tasks complete and
review-clean; Task 14 is a committed WIP that still needs finishing + its review.**
All on branch **`claude/phase2a-design`**, `main` untouched, Phase 1 frozen.

### State at session close
- **Branch tip:** `9b19df5` — **28 commits ahead of `main`**.
- **Full Phase 2A suite: 47 passed** (`.venv\Scripts\python.exe -m pytest tests/phase2a`).
  Phase 1 suite expected **18 passed** (`pytest phase1_cdr/tests`).
- **Phase 1 is frozen:** `git diff --stat main -- phase1_cdr/` is **EMPTY** (the
  branch never touched `phase1_cdr/`). The whole `app/` package + `main.py` are new.
- **Working tree clean** apart from the SDD ledger and untracked `.claude/` +
  `session-logs/`.

### What's built (all committed, all reviewed except Task 14)
`app/`: `config.py` (Task 1), `crypto.py` (2), `storage.py` (3, SQLCipher + on-disk
encryption proof), `account.py` (4, envelope key mgmt), `audit.py` (5), `__init__.py`
(6, factory + sessions + get_db + ok/err envelope + login_required), `auth.py` (7),
`validation.py` (8), `imports.py` (9, xlsx import + datasets), `targets.py` (10),
`detection_bridge.py` (11, the ONLY seam to phase1, equivalence-tested),
`analysis.py` (12). Root `main.py` (13, Flask thread + PyWebView). All 4 blueprints
registered. End-to-end works: User A → home "Hamra"/High through the full stack.

### CRITICAL environment + baseline notes for next session
1. **Interpreter:** `C:\Users\nadim\OneDrive\Desktop\la passion\.venv\Scripts\python.exe`
   (Python 3.11.9 **ARM64**, new root venv). **NEVER use `phase1_cdr/.venv`** — its
   numpy/pandas DLLs are blocked by Windows Application Control. `cryptography==46.0.3`
   (49.x fails the ARM64 Rust build; APIs compatible). `sqlcipher3` import verified
   (`sqlcipher ok 3.51.1`).
2. **FROZEN-PHASE1 BASELINE IS `main`, NOT the `v1.0-phase1` TAG.** The tag predates
   the merged 9-column frequency feature (tag=6 cols, main=9). Any "is phase1
   untouched?" check MUST diff against `main`. The plan's Task 14 Step 4 names the tag
   — that is a plan bug; use `main`.

### EXACT resume instructions
1. `git checkout claude/phase2a-design` (tip `9b19df5`).
2. Re-invoke **superpowers:subagent-driven-development**. Read the ledger
   `.superpowers/sdd/progress.md` first — Tasks 1–13 are DONE (don't re-run them).
3. **Finish Task 14** (it's a committed WIP at `9b19df5`, NOT yet reviewed). Remaining
   steps a–f are spelled out in the ledger's "Task 14: PARTIAL" entry: add the README
   Phase 2A section, run + record both suites, verify `git diff --stat main --
   phase1_cdr/` is empty, commit the README, then run the Task 14 review gate over the
   two new test files in `9b19df5`.
4. **Then the final whole-branch review** (Task 15 in the SDD todo list): dispatch the
   broad code-reviewer over `git merge-base main HEAD..HEAD`, triage the deferred-minor
   list (in the ledger), fix Critical/Important, then **superpowers:finishing-a-
   development-branch**. Per COLLAB.md: stay on the `claude/` branch; Codex reviews;
   **only Nadim merges to `main`**.

### Decisions Nadim made mid-execution (do NOT re-litigate)
- **Task 4:** hardened `authenticate` to constant-time (always run bcrypt +
  `hmac.compare_digest`) to kill a username-enumeration timing oracle; added a
  `change_password` no-account guard. Done.
- **Task 7:** the implementer had turned the `_404` handler into a global auth-wall to
  satisfy a **mis-sequenced** plan test (`test_protected_route_requires_login` asserted
  401 on `/api/targets`, which doesn't exist until Task 10). Reverted to plain 404;
  retargeted the test to `POST /api/logout`. Done. Do NOT re-add the /api/targets 401.

### For Codex
The branch is implementation-complete except Task 14's finish + two review gates. The
per-task diffs are in `git log`; per-task reviewer notes + the deferred-minor roll-up
are in `.superpowers/sdd/progress.md`. Worth a read before the final review.

---

## 2026-06-24 (session 2) — Claude: Phase 2A design + plan complete; SDD execution NOT yet started

Brainstormed, spec'd, and wrote a full implementation plan for **Phase 2A —
Backend Foundation**. **No application code written yet** — the next session
starts executing the plan. Everything is on branch **`claude/phase2a-design`**
(pushed to origin), `main` untouched.

### What exists now (all committed on `claude/phase2a-design`)
- **Spec:** `docs/superpowers/specs/2026-06-24-phase2a-backend-design.md`
  (commits `569bb33` + fix `7c987a4`).
- **Plan:** `docs/superpowers/plans/2026-06-24-phase2a-backend-foundation.md`
  (commit `f252f1e`) — **14 TDD tasks**, full code in every step.
- Branch tip: `f252f1e`. Three commits ahead of `main`; zero `phase1_cdr/`
  changes (Phase 1 stays byte-identical to tag `v1.0-phase1`).

### Decisions locked during brainstorming (do not re-litigate)
1. **9-column CDR schema** for import/storage (matches v1.0; the prompt's older
   6-col list was wrong — frequent-contacts needs `other_party`).
2. **Single account** per install.
3. **SQLCipher via `sqlcipher3-wheels`** — the only binding with prebuilt Windows
   wheels (official `sqlcipher3-binary` is Linux-only; `pysqlcipher3` needs a VS
   build). SQLCipher 4, self-contained, Py 3.11 ✓.
4. **Envelope key management** — random 256-bit DB key, AES-GCM-wrapped by a
   scrypt-derived KEK from the password; bcrypt is the password verifier. Raw
   db_key never on disk. Non-secret `auth.json` sidecar holds
   {username, bcrypt_hash, kdf_salt, db_key_nonce, wrapped_db_key, created_at}.
5. **First-run `POST /api/setup`** (409 once an account exists).
6. **change-password endpoint: IN.** Login lockout: OUT (YAGNI, localhost).
7. **Delete-dataset endpoint: IN.** Analysis response exposes the **full gate
   trace** (gates/share/closeness/density), not just headline confidence.
8. Targets are **`UNIQUE(dataset_id, phone_number)`** — name is a label, not an
   identity key; duplicate create → 409.

### EXACT resume instructions (next session)
1. `git fetch && git checkout claude/phase2a-design` (tip should be `f252f1e`).
2. Re-invoke **superpowers:subagent-driven-development** on the plan file above.
3. **Progress ledger:** `.superpowers/sdd/progress.md` — currently **0 of 14
   tasks complete**. Resume at **Task 1** (deps/config/gitignore). If the ledger
   is gone (`git clean`), trust `git log` — anything past `f252f1e` is done work.
4. **Task 1 Step 2 is a hard gate:** `pip install -r requirements.txt` then
   import-check `sqlcipher3` on this Windows machine BEFORE relying on it. If that
   import fails, stop and resolve it first — all 14 tasks rest on it.
5. Plan has one deliberate wrinkle (documented in Task 6): the app factory
   registers 4 blueprints that don't exist until Tasks 7–12 → comment them out,
   get Task 6 green, uncomment each as its task lands.
6. Per `COLLAB.md`: stay on the `claude/` branch, Codex reviews the diff, only
   Nadim merges to `main`.

### For Codex
The branch is review-ready as a **design + plan** (no app code yet). Worth a read
of the spec + plan now if you want to flag anything before implementation; the
implementation diff will come task-by-task next session.

---

## 2026-06-24 — Claude: session close — three branches merged, brief committed, methodology backlog filed

Wrap-up of the day's merges + bookkeeping, all authorized by Nadim. No
code-under-test changes by me; everything is now on `main` (`306caa8`), green.

- **Three fast-forward merges to `main` (Nadim's call):** `frequency-branch`
  (the 9-column schema + frequency feature), `codex/frequency-query-review`
  (Codex's review — added a final-tie-break unit test + a 6→9 doc fix; suite
  18 passed / 34/34), and `codex/methodology-assessment` (Codex's domain-logic
  analysis — entry below). All three branches deleted local+remote after merge.
- **`EXPERT_BRIEF.md` committed to `main`** (`306caa8`). It had been **untracked**
  — invisible to Codex, since git is our only shared memory. Updated to the
  9-column schema, added the frequent-contacts output to §3, refreshed the count
  to 34/34 + 18 unit tests. Now ready for an outside CDR expert.
- **Methodology backlog filed from Codex's assessment:** Issues **#7**
  (candidate-specific Density — note User E must be re-derived), **#8**
  (window-fit diagnostics), **#9** (whole-distribution concentration metric —
  refines #2.1), **#10** (report binding gate(s) + weak-gate count — refines
  #2.2). #2 kept open as the parent design note with a comment linking #9/#10.
- **Discussed (no change):** whether multiple gates can be Low at once. They can
  — gates aren't mutually exclusive (N↔Density align on sparse-long-span;
  Share↔Closeness *correlate* on a fragmented field). A ~12-events-over-200-days
  subscriber trips all four Low. This is the rationale behind #10.

**State:** `main` is the only branch, clean, green. Backlog = Issues #1/#2 +
#7–#10, all deferred to real-data calibration, none blocking.

**For Codex:** your methodology assessment and frequency review were both
accepted and are on `main` now — `git fetch` to resync; your stale local branches
are gone from the remote (`git fetch --prune`).

---

## 2026-06-24 - Codex: methodology assessment of CDR inference (branch `codex/methodology-assessment`)

Ran `git fetch --all` first, read `COLLAB.md` and `HANDOFF.md` from fetched
`origin/main`, then branched from `origin/main` (`0563ad3`). Read the root
`README.md`, `phase1_cdr/README.md`, `phase1_cdr/detection.py`,
`docs/superpowers/specs/2026-06-23-frequency-query-contacts-design.md`, and the
local `EXPERT_BRIEF.md`.

Scope note: this is **not** a code review. I am not a telecom/CDR domain expert,
so the judgments below are about internal methodological soundness: whether the
logic is coherent, what assumptions it relies on, and which conclusions cannot be
settled without real CDR domain expertise or real data.

**SOUND**
- The baseline is transparent: fixed windows propose candidate contexts, plurality
  selects the area, and the confidence gates decide how much to trust that area.
  That separation is methodologically clean for Phase 1 because it avoids hiding
  the inference behind a black-box score.
- The home/work/frequent split is coherent as a first heuristic. Overnight events
  are a plausible home proxy; weekday daytime events are a plausible work proxy;
  all-record frequent areas are descriptive habits rather than a single anchor.
- The four gate names map to real failure modes: not enough records (`N`), weak
  dominance (`Share`), ambiguity against the runner-up (`Closeness`), and sparse
  temporal coverage (`Density`). This is a better design than share-only confidence.
- `N` and `Density` are meaningfully distinct in intent. `N` is an absolute sample
  floor; `Density` asks whether evidence is spread across the observation span. The
  choice of distinct active days instead of raw event count is sounder than raw
  events because it does not let one unusually busy day masquerade as broad support.
- The weakest-link `min()` aggregation is defensible as a conservative Phase 1
  label. If any gate captures a fatal weakness, letting stronger gates average it
  away would overstate confidence.
- Near-tie alternatives are methodologically important. Returning the plurality
  while tagging close alternatives is better than silently pretending a split
  anchor is a clean single-location answer.
- The new frequent-contacts output is meaningful if framed as descriptive analytics:
  "these are the counterparties with the most events, split by event type." It is
  not a location inference and should not inherit the confidence-gate language.

**QUESTIONABLE**
- The fixed home/work windows are plausible but brittle. Night-shift workers,
  students, remote workers, healthcare/hospitality schedules, dual residences,
  travel, roaming, and timestamp timezone mistakes can all produce enough data to
  look confident inside the wrong window. The current gates measure strength inside
  a window; they do not test whether the window itself fits the subscriber.
- A cross-check is worth adding. For home, I would not require "dominates weekend
  daytime" because weekends include leisure/travel, but the home candidate should
  be tested for support in weekend overnight, late evening, and across multiple
  weeks. For work, test weekday daytime consistency across weeks and look for a
  competing weekend/daytime or evening anchor that suggests a non-standard schedule.
- Plurality-takes-all is too crude as the only winner-selection story. It is clear
  and reproducible, but "most events in the window" is not necessarily "best anchor"
  when area labels are noisy, adjacent cells split a real place, or one macro-area
  covers multiple plausible locations. The method should expose the candidate
  distribution, not just the top label.
- The deterministic tie-break is useful for reproducibility but has no evidentiary
  meaning. Earliest timestamp should never be interpreted as support for the winner;
  it is only an ordering fallback.
- `Share` and `Closeness` are not identical, but they overlap. A dominant winner
  mechanically tends to produce a small runner-up ratio. `Share` catches "winner is
  only a small slice of a fragmented field"; `Closeness` catches "#2 is too close."
  Both are useful, but together they partly double-count dominance/ambiguity.
- `Closeness` only looks at #1 versus #2. It misses multi-way fragmentation where
  no single runner-up is close but the tail is broad. A concentration metric over
  the whole distribution (entropy, HHI/effective-number-of-areas, or top-k mass)
  would measure this more directly.
- `min()` is conservative, but the final label is lossy. One Medium gate and four
  Medium gates both report Medium; one Low gate and four Low gates both report Low.
  The implementation exposes `gates`, but the headline confidence should probably
  carry the binding gate(s) and/or a weakness count.
- Current `Density` measures distinct active days in the selected time window, not
  distinct days supporting the winning area. That adds temporal signal beyond `N`,
  but it can be inflated by activity in non-winning areas. A candidate-specific
  density such as "days where the winning area appears / observed days" would align
  better with "how much evidence supports this inferred anchor."

**NAIVE / MISSING**
- The `area` idealization is the biggest assumption. The method treats `area` as a
  clean, opaque, one-area-per-event label. Real serving-cell data has overlapping
  footprints, variable cell sizes, load/radio effects, handovers, sectorization,
  and network changes. The confidence model is only as meaningful as the upstream
  process that turns cells into stable areas.
- `Share` and `Closeness` are the most fragile gates under realistic cell data.
  Dense-cell areas can fragment one real place across many cells and look low-share
  or near-tied; a large macrocell can create high share while being geographically
  imprecise. These gates may measure network topology as much as user behavior.
- The model lacks temporal stability checks. A home/work anchor should ideally be
  stable across subperiods, not just win in aggregate. A vacation, short project,
  or burst of calls can dominate an aggregate window while being temporally local.
- Observation span is inferred from first-to-last event. For event-triggered CDRs,
  that is not the same as a known export window or true monitoring span. If a data
  extract has explicit start/end dates, Density should use those instead.
- Ignoring `call_type`, `duration_seconds`, and `imei` is defensible for a clean
  baseline, but it leaves useful diagnostics on the table. `imei` can reveal device
  changes, shared SIM/device anomalies, or mixed-user histories. `call_type` and
  duration may reveal event-source biases, although weighting by them should wait
  for real source semantics.
- Direction/duration should not be naively weighted. A 20-minute call is not
  automatically 120 times stronger than a 10-second call; depending on CDR
  semantics, location may be start-cell, end-cell, or affected by handover. If used,
  duration should be capped or handled as a separate diagnostic until validated.
- Frequent contacts are currently a count, not relationship inference. Total event
  volume can be distorted by SMS bursts, service/short codes, spam, business calls,
  observation length, or one person using multiple numbers. The 4-way split helps,
  but it does not by itself establish closeness or importance.
- `EXPERT_BRIEF.md` is aligned with the right open questions, but it still describes
  the older 6-column schema while `main` now has 9 columns. Before external expert
  review, update that brief so the expert does not reason from stale schema scope.

**NEEDS REAL DOMAIN EXPERTISE OR REAL DATA**
- Whether 00:00-06:00 and weekday 09:00-18:00 are good windows for the target
  population cannot be settled internally. It depends on local schedules, timestamp
  timezone conventions, roaming behavior, and the intended investigative use case.
- `N_HIGH=50`, `N_MEDIUM=15`, `DENSITY_HIGH=0.40`, and `DENSITY_MEDIUM=0.15` should
  be treated as fixture-calibrated labels, not general confidence. Real CDR event
  volumes are event-triggered and likely heavy-tailed by subscriber, plan, period,
  app usage, and operator logging rules.
- Share and Closeness are not truly scale-free until `area` granularity is fixed.
  Changing from neighborhood labels to raw Cell-ID, sectors, clustered cells, or
  geocoded zones will change the expected concentration distribution.
- The right upstream `area` derivation needs telecom expertise: raw Cell-ID vs cell
  clusters vs geocoded zones, how to handle overlapping cells, and whether to use
  tower/sector metadata or radio measurements if available.
- Whether `call_type` and duration should influence location evidence depends on
  source-system semantics: which events carry location, whether the logged cell is
  start/end/serving cell, and whether SMS/voice/incoming/outgoing records have
  comparable location reliability.
- Frequent-contacts ranking needs real data to decide filtering and meaning:
  service numbers, short codes, duplicated people across numbers, corporate phones,
  and direction/duration conventions can all change what "top contact" means.

**RECOMMENDATIONS**
1. Keep the current method as a transparent baseline, but label the confidence as
   "fixture-calibrated" until real distributions exist. Do not present it as a
   probability or production-quality confidence score.
2. Add window-fit diagnostics before changing the core detector: weekend overnight
   support for home, weekday/weekend contrasts, weekly stability, and warnings for
   schedules that do not resemble the fixed home/work assumptions.
3. Keep plurality as the first candidate selector, but always surface the top-k
   distribution. Treat a single area answer plus hidden tail as too little evidence
   for human interpretation.
4. Replace or augment `Share`/`Closeness` with a whole-distribution concentration
   measure during the next methodology pass. Entropy, HHI/effective number of areas,
   top-1 minus top-2 margin, and top-k mass are all worth comparing on synthetic
   adversarial cases before touching real data.
5. Keep weakest-link `min()` as the conservative floor, but report the gate vector,
   binding gate(s), and number of weak gates beside the headline confidence. Consider
   a second severity label for "many gates weak" rather than overloading High/Medium/Low.
6. Rework Density to be candidate-specific and tied to a known extract span where
   available: distinct days with winning-area evidence over export days. Keep raw
   event volume out of Density so it remains distinct from `N`.
7. Treat `area` derivation as a separate modeling layer with its own tests. Before
   trusting confidence, simulate realistic cell artifacts: adjacent-cell splitting,
   macrocell dominance, handover/oscillation, and cell-ID churn.
8. Audit `call_type`, `duration_seconds`, and `imei` empirically before weighting.
   Start with diagnostics/segmentation (for example, "home only appears on SMS" or
   "work changes after IMEI switch") rather than changing scores immediately.
9. Reframe frequent contacts explicitly as descriptive counts. If it will support
   analytical conclusions, add active-days-per-contact, recency, voice duration,
   direction balance, service-number filtering, and possibly entity resolution.

No code changes or merge performed. This branch changes only `HANDOFF.md`.

---

## 2026-06-24 - Codex: independent review of merged frequency feature (branch `codex/frequency-query-review`)

Reviewed fetched `main` directly after `git fetch --all` + `git fetch --prune`.
Commit range was `aee46da` (design), `87606d9` (feature), `0aa3d1b` (merge
handoff). No merge performed.

**Verdicts**
- **RNG isolation: CONFIRMED.** I compared git blobs for
  `phase1_cdr/sample_data.csv` at `f2fac0e` and `HEAD`, projecting only the
  original 6 columns (`phone_number,imei,area,timestamp,call_type,duration_seconds`):
  byte-for-byte equal projection, 216550 bytes on both sides. Parsed
  `phase1_cdr/ground_truth.json` from both revisions: all five users' `home` and
  `work` blocks are exactly equal. The separate contact stream is present at
  `phase1_cdr/dev_fixtures.py:58` and used only for counterparty assignment at
  `phase1_cdr/dev_fixtures.py:150`; it does not perturb the main `random` stream.
- **Contacts ground truth: ACCEPTABLE WITH CAVEAT.** I rederived contacts from
  `sample_data.csv` using stdlib `csv` + counters only (no `detection.py`, no
  `dev_fixtures._contacts`) and matched `ground_truth.json` for all five users.
  Spot examples: User A top two are `03200101` total 481 = 106/118/125/132 and
  `03200102` total 284 = 69/66/66/83; User D top two are `03200401` total 334 =
  68/93/98/75 and `03200402` total 279 = 84/64/76/55. Every contact rank's
  `total` equals the sum of the four buckets. Caveat: `_contacts()` at
  `phase1_cdr/dev_fixtures.py:277` is intentionally close to
  `detect_frequent_contacts()` at `phase1_cdr/detection.py:282`, so it proves
  implementation consistency more than conceptual correctness. That is acceptable
  for generated fixture ground truth because the hand-written unit tests also pin
  the mapping and sort behavior.

**Bugs**
- None found in the merged feature behavior.

**Test gaps**
- The generated fixture has no contact ties, so `sample_data.csv`/the harness do
  not exercise the tie-break. Code is correct at `phase1_cdr/detection.py:310`.
  Fixed on this Codex branch by adding the missing final-key unit test at
  `phase1_cdr/tests/test_detection.py:208` (same total + same earliest timestamp
  -> lower number wins). Existing tests already cover total ranking and 4-way
  buckets at `phase1_cdr/tests/test_detection.py:179`, plus earliest-timestamp
  tie-break at `phase1_cdr/tests/test_detection.py:198`.

**Correctness concerns**
- **Call-type labels:** I do not think the generated harness should be the thing
  that pins `1/2/11/22 -> call_out/call_in/sms_out/sms_in`; because it is generated
  by `_contacts()`, that would still share conceptual errors. The current hardcoded
  convention is fine if kept explicit in `phase1_cdr/loader.py:26` and
  `phase1_cdr/detection.py:105`, with the hand-written unit test at
  `phase1_cdr/tests/test_detection.py:179` serving as the real guard. If stronger
  independence is wanted later, add a tiny hand-authored CSV/ground-truth fixture,
  not another generated check.
- **Unused schema columns:** `phase1_cdr/loader.py:14` requires all 9 columns and
  fails missing ones at `phase1_cdr/loader.py:61`, while `other_imei`/`other_area`
  are documented as carried-but-unused at `phase1_cdr/README.md:53`. My lean:
  acceptable if the real generator contract has intentionally moved to 9 columns;
  otherwise it is integration risk because valid home/work/frequent-area data will
  be rejected only for missing unused columns. Related later hardening: if the real
  generator can emit blank `other_party`, pandas `groupby("other_party")` at
  `phase1_cdr/detection.py:296` will drop null counterparties silently unless the
  loader rejects or normalizes them.

**Nits**
- `phase1_cdr/dev_fixtures.py:11` still said the future generator must emit the
  old 6-column schema. Fixed on this Codex branch to 9-column.

**Verification**
- `phase1_cdr/.venv`: `python -m pytest tests` -> **18 passed** (17 existing +
  the new tie-break test).
- `phase1_cdr/.venv`: `python main.py sample_data.csv ground_truth.json` ->
  **34/34 (100%)**.

---

## 2026-06-24 — Claude: `frequency-branch` rebased onto `main` + fast-forward MERGED (Nadim's call)

Closes the frequency-query feature. Authorized explicitly by Nadim this session
(Option B from the 2026-06-23 session log).

- **Re-verified green before merge** (in `phase1_cdr/.venv`, pandas 3.0.3):
  `pytest tests/` → **17 passed**; `python main.py sample_data.csv
  ground_truth.json` → **34/34 (100%)**.
- **Option B (skip remote churn).** The branch was already rebased onto `main`
  last session (linear, `main` 0 behind), so the merge is a trivial
  fast-forward. Merged `frequency-branch` → `main` and pushed. The shared
  `origin/frequency-branch` (Khaled's OLD pre-rebase tip) is now irrelevant and
  deleted; the pre-rebase tip is preserved at `a8959611` if rollback is ever
  needed.
- **Codex** still hasn't seen the frequency work, the review, or the rebase — it
  syncs now via `git fetch` on `main`.

**State:** `main` carries the 9-column schema + frequency query (locations %% +
ranked contacts). Standing future work unchanged: Issues #1 (`N_*`/`DENSITY_*`
re-tune) and #2 (`min()` design notes); `EXPERT_BRIEF.md` is queued for outside
CDR-domain review.

---

## 2026-06-23 — Claude: frequency query extended — locations %% + ranked contacts (branch `frequency-branch`)

**New feature branch `frequency-branch`**, originally cut from `branched-out-dih`
(NOT from `main`) because it built on the then-unmerged confidence work.
**[CORRECTION 2026-06-24: rebased onto `main` and fast-forward-merged — see the
entry above. The branch no longer sits on `branched-out-dih`.]** Design spec
committed first at `docs/superpowers/specs/2026-06-23-frequency-query-contacts-design.md`.

**What changed (per Khaled's spec):** the "frequent" query now reports two things —
(1) top-5 **locations with percentages**, and (2) a new top-5 **contacts** ranking:
the counterparty numbers the subject communicated with, ranked by total, each split
**4-way by `call_type`** (1 call-out / 2 call-in / 11 SMS-out / 22 SMS-in).

- **Schema 6 → 9 columns.** Added `other_party`, `other_imei`, `other_area`
  (`loader.py:14`, `:27`). Every query stays single-subject; only `other_party` is
  read by a query (contacts). `other_imei`/`other_area` are carried but unused yet —
  Khaled's explicit scope call.
- **`detection.py`** — new `ContactRank` dataclass + `detect_frequent_contacts(df,
  top_n=5)` (`detection.py:104`, `:259`). Pure, no gates (raw frequency ranking,
  like `detect_frequent_areas`). Same deterministic tie-break as `_sorted_areas`
  (total desc → earliest ts → number asc). `detect_frequent_areas` default `top_n`
  3 → 5.
- **`dev_fixtures.py`** — per-user `CONTACTS` pools + a SEPARATE `_contact_rng`
  (`dev_fixtures.py:54`). **Key invariant:** contact draws use their own RNG, so the
  main stream (dates/hours/call_types/areas) is byte-identical to before. Verified:
  `git show HEAD:...sample_data.csv | cut -d, -f1-6` is identical to the new file,
  and the ground-truth home/work/confidence blocks are unchanged in the diff. Only
  `frequent` expanded to 5 and a `contacts` block was added per user. Ground truth
  for contacts is independently tallied by `_contacts()` (plain groupby, no
  `detection.py` import).
- **`validate.py` / `main.py`** — new `validate_contacts()` (one PASS/FAIL row per
  contact rank so the breakdown is visible); `_check_frequent` now shows each area's
  %. `main.py` prints two tables and a combined summary.
- **Tests** — 4 new unit tests for `detect_frequent_contacts` (rank, 4-way split,
  tie-break, top_n cap). TDD: tests written first, watched fail (ImportError), then
  implemented.

**Verified (executed in `phase1_cdr/.venv`):** `pytest tests/` → **17 passed**;
`python main.py sample_data.csv ground_truth.json` → **34/34 (100%)**. The 12 prior
home/work/frequent/confidence checks still pass unchanged; the rest are the new
per-rank contact checks.

**For Codex:** independently re-derive a couple of users' top-5 contacts from the
fixture `CONTACTS` weights vs the committed `ground_truth.json`, and sanity-check the
RNG-isolation claim (that the old 6 columns are untouched). Do NOT merge — this is a
fresh feature branch off `branched-out-dih`; Nadim merges. **[DONE 2026-06-24 —
merged by Nadim; see top entry.]** Open question: do we want
the contacts harness to also pin which `call_type` maps to which label, or is the
fixed `1/2/11/22` convention enough?

---

## 2026-06-22 — Claude: merged Dependabot CI bump (PR #4) + pruned merged branches

Housekeeping session, authorized by Nadim. No algorithm/code-under-test changes.

- **PR #4 merged** (`de0a05d`): grouped github-actions bump in `.github/workflows/ci.yml`
  — `actions/checkout` v4→v7, `actions/setup-python` v5→v6. Both CI `test` checks
  green on the new versions before merge. The 2-dot diff *appeared* to also revert
  this HANDOFF's session-close entry, but that was a stale-branch artifact: the
  branch's merge-base was `e1746a2` and it touched only `ci.yml`, so the 3-way merge
  left HANDOFF.md untouched (verified post-merge).
- **Stale branches pruned** (all fully merged into `main`, zero unmerged commits):
  remote `branched-out-dih`, remote `claude/ci-github-actions`, local
  `codex/review-branched-out-dih`, and the auto-deleted Dependabot branch.

**State:** `main` is the only branch (plus this one), green, Phase 1 still shipped at
`v1.0-phase1`. Standing future work unchanged: Issues #1 (re-tune `N_*`/`DENSITY_*`)
and #2 (`min()` design notes).

---

## 2026-06-21 — Claude: session close — Phase 1 shipped & tagged; branch protection skipped

Final state at end of session. Everything below is on `main` and green.

- **PR #3 merged** (`claude/repo-hardening` → `main`, commit `e1746a2`): root
  `README.md`, `.github/dependabot.yml`, `.github/PULL_REQUEST_TEMPLATE.md`. First
  clean run through the PR flow.
- **`v1.0-phase1`** annotated tag pushed, and a **GitHub Release** published from it
  (release notes on the repo sidebar).
- **Dependabot** security alerts + auto-fixes enabled; Issues **#1** (threshold
  re-tune) and **#2** (`min()` design notes) are the canonical tracker for the
  standing items now.
- **Branch protection: SKIPPED.** Rulesets/classic protection are plan-gated on a
  free private repo (403 "Upgrade to GitHub Pro or make this repository public").
  Per Nadim, we rely on the honor-system PR flow in `COLLAB.md` instead. If the repo
  later goes public or Pro, add a ruleset on `main` requiring the `test` check + a PR
  with an admin bypass — that's the only missing piece. (Saved as a project memory so
  it isn't re-attempted.)

**Phase 1 is complete.** Next work (when picked up) is Issues #1/#2 or Phase 2.

---

## 2026-06-21 — Claude: repo hardening — root README, Dependabot, PR template, Issues, branch protection (branch `claude/repo-hardening`)

Portfolio + process hardening, approved by Nadim. Several pieces are GitHub-state
(not file commits); the file changes are on this branch as a PR — the **first run
through the new PR-based merge flow** below.

**Files on this branch:**
- **Root `README.md` (new)** — the repo had no top-level README, so the GitHub
  landing page showed a bare file list and the CI badge (in `phase1_cdr/README.md`)
  wasn't visible there. New root README frames the multi-phase vision, the
  four-gate model, and the two-agent collaboration workflow, and carries the badge.
- **`.github/dependabot.yml` (new)** — pip ecosystem on `/phase1_cdr`, github-actions
  on `/`, both **monthly + grouped** to avoid PR noise on a 3-dep project. The
  github-actions entry also auto-clears the "Node 20 deprecated" CI warning when
  newer action majors ship.
- **`.github/PULL_REQUEST_TEMPLATE.md` (new)** — reinforces the protocol at merge
  time (CI green / other agent reviewed / HANDOFF updated / no status in COLLAB).

**GitHub-state changes (already applied, not in the diff):**
- **Dependabot security alerts + automated security fixes** enabled on the repo.
- **Issues opened for the standing items** (migrated out of this log so they're
  visible + closeable): **#1** re-tune `N_*`/`DENSITY_*` on the real generator;
  **#2** the two `min()` confidence-design notes. These are the canonical tracker
  now — this log just points at them.
- **Annotated tag `v1.0-phase1`** marking Phase 1 complete — applied **after this
  PR merges** so the milestone captures the documented state.
- **Branch protection on `main`** — intended: require the CI status check + a PR
  before merge, with an admin bypass for Nadim. **[CORRECTION 2026-06-21: NOT
  applied — plan-gated (free private repo → 403, needs Pro or public). Nadim chose
  to SKIP enforcement. See the session-close entry above.]**

**Workflow note:** with branch protection live, the normal path is now PR →
CI green → Nadim merges. Agents still never merge.

**Next:** Codex reviews this PR; Nadim merges it; then I apply the
`v1.0-phase1` tag.

---

## 2026-06-21 — Claude: added GitHub Actions CI (branch `claude/ci-github-actions`)

Closes the standing open item from the merge: the test suite no longer depends
on one machine being able to load pandas.

**What changed:** new `.github/workflows/ci.yml`. Triggers on **every push and
every pull request** (no branch filter — covers `main`, the feature branches,
and review PRs). On `ubuntu-latest` with **Python 3.12** (matches Khaled's
verified 3.12.10), it:
1. installs `phase1_cdr/requirements.txt` (pip cached on that file's hash),
2. runs `pytest tests/`,
3. runs the validation harness `python main.py sample_data.csv ground_truth.json`.

Setup was read off the existing structure, not assumed: all steps use
`working-directory: phase1_cdr` because that's where `requirements.txt`, `tests/`,
and `conftest.py` live (conftest puts that dir on `sys.path` so tests import
`detection`/`loader` directly). Harness step included on purpose — `main.py`
exits non-zero on any failure, so CI enforces the real 12/12 integration check,
not just the 13 unit tests.

**Verification:** ubuntu's Python loads pandas fine, so the push that creates
this branch is itself the first live CI run — watch the Actions tab. I could not
run `pytest` locally (pandas still blocked by Windows Application Control on this
machine), which is exactly the dependency this CI removes.

**Next:** per protocol, not merged. Codex reviews the workflow, then Nadim merges
`claude/ci-github-actions` to `main`. Once green, add a status badge to the
README if Nadim wants one.

---

## 2026-06-21 — Claude: doc-drift fix applied (option 2) + `branched-out-dih` MERGED to `main` (Nadim's call)

Two things, both authorized explicitly by Nadim this session.

**1. Doc-drift fix — option 2.** Nadim chose the self-enforcing convention from
the open question below. Implemented in `COLLAB.md`:
- Added **rule 3** under "Two rules that prevent disaster": *"`COLLAB.md` is
  rules-only. Any branch or merge status goes in `HANDOFF.md`, never here. If you
  find status text in `COLLAB.md`, move it."*
- Replaced the `Current active branch` subsection (which carried a mutable commit
  list + Status line) with a stable pointer to `HANDOFF.md`'s top entry.
The mutable status now lives in exactly one place, so the protocol doc can't go
stale and contradict the running log again. The open question below is now
**resolved** — kept for the record.

**2. Merge to `main`.** With the verification green (13 passed / 12/12) and both
agents agreed, **Nadim gave explicit permission to merge**. Merged
`branched-out-dih` → `main` and pushed. `main` now carries the full four-gate
confidence model. The feature branch has served its purpose.

**Next:** Phase 1's confidence work is done and on `main`. Standing open items
for whoever picks up next (none are blockers): re-tune `N_*` / `DENSITY_*` once
the team's real synthetic generator fixes the true volume/span distribution; the
two `min()`-design notes (Share/Closeness overlap; `min()` blind to how many
gates are weak), both deferred to real-data calibration; and consider a GitHub
Actions CI (`pytest` on push) so the suite no longer depends on one machine being
able to load pandas.

---

## 2026-06-21 — Claude: QUESTION for Nadim — should branch status live ONLY in `HANDOFF.md`? [RESOLVED — option 2, see entry above]

**Not a change request — asking before doing anything structural.** I only
updated the Status line in `COLLAB.md`'s `Current active branch` subsection to
reflect today's green run. I did NOT restructure that file. The question below is
open for your call.

**The issue.** Our two docs have distinct jobs: `COLLAB.md` = stable *protocol*
(the rules you paste to an agent at session start); `HANDOFF.md` = the *running
intent log* (mutable, newest-on-top state). But `COLLAB.md`'s `Current active
branch` subsection carries mutable state — a numbered list of the commits on the
branch plus a **Status** line. That's a snapshot, not a rule, so it lives in the
file that's *supposed* to be stable.

**Why it just bit us.** Before I touched it, `HANDOFF.md` correctly said the
branch was verified merge-ready after the green run, but `COLLAB.md` still said
"merge-ready pending one verification run." The two docs contradicted each other —
and the *protocol* doc (the one we paste FIRST when onboarding an agent) was the
stale one, understating progress. Per our own core principle (each agent's view
is a frozen snapshot; git is the only shared memory), a fresh Claude/Codex
session reading `COLLAB.md` first could conclude the run still needs doing and
redo it — not realizing it's already green. Root cause is structural: **mutable
state living in the file meant for stable rules.** Updating the status line (as I
just did) fixes it for now but the drift will recur next time work advances.

**The question — do we want a durable fix?** Options, lightest → heaviest:
1. **Do nothing structural** — keep updating the `COLLAB.md` status line by hand
   each session. Simplest; the drift just keeps coming back.
2. **Add a rule to `COLLAB.md`** under "Two rules that prevent disaster":
   *"`COLLAB.md` is rules-only. Any branch/merge status goes in `HANDOFF.md`. If
   you find status text in `COLLAB.md`, move it."* Then trim the `Current active
   branch` subsection down to a stable pointer at `HANDOFF.md`. Self-enforcing
   for any agent that reads the protocol.
3. **Single source of truth** — pin one `## STATUS` block at the very top of
   `HANDOFF.md` that every handoff updates in place, so no one scans entries to
   learn the current state.
My lean is **#2**, but this is your call, Nadim — say the word and I'll implement
whichever you pick. Nothing structural changed yet.

---

## 2026-06-21 — Khaled/Claude: verification run GREEN — branch confirmed merge-ready

Ran the only remaining gate on `branched-out-dih` at HEAD `a636071`, in
`phase1_cdr/.venv` (Python 3.12.10, pandas 3.0.3 — loads fine):
- `pytest tests/` → **13 passed** (matches the expected 13).
- `python main.py sample_data.csv ground_truth.json` → **12/12 passed (100%)**
  (matches the expected 12; E-work row included).

Per-user results line up with Codex's independent gate trace: A home/work High;
B home `Low: near tie` (alt Hamra) / work Medium; C home/work `Insufficient
data`; D home `Low: near tie` (alt Achrafieh) / work `Low: near tie` (alts
Mazraa/Verdun); E home `Low` (Density-bound) / work `Insufficient data`.

**State:** the static trace is now confirmed by execution at HEAD. Nothing
changed in code — this entry only records the green run. Branch is **agreed by
both agents and verified**; the next action is **Nadim merges `branched-out-dih`
to `main`**. I did NOT merge (per protocol, only Nadim merges).

---

## 2026-06-20 — Claude: folded Codex's review into `branched-out-dih` (merge-ready)

Reviewed Codex's commit `f7d7d9b` (originally on local branch
`codex/review-branched-out-dih`) and traced it against the fixtures. **Agreed
with all of it** — the `validate.py` null-area fix is the correct root-cause fix
for the bug flagged in the first review; C/E tightening to exact `Insufficient
data` is correct (C is evening-only, E has no weekday-daytime records, so both
windows are genuinely empty); the near-tie unit-test rescale (6/5 → 30/25)
correctly re-isolates the closeness gate after `N_MEDIUM` rose to 15.

Codex could not push (its sandbox approval policy blocks outbound network to the
GitHub remote), so the commit was local-only. Since it's a clean +1 fast-forward
and is reviewed/approved, per Nadim's call I **fast-forwarded `branched-out-dih`
to `f7d7d9b` and pushed** — no separate review branch is kept. `origin/branched-
out-dih` now ends at `f7d7d9b`; Khaled can pull it.

**State:** branch is the agreed state of both agents, **merge-ready pending one
re-run.** Ground truth + harness logic + tests all changed since Khaled's last
green run, so his 11/11 no longer covers HEAD.

**Next (the only remaining gate):** Khaled pulls `branched-out-dih`, runs
`pytest tests/` (expect **13 passed**) and `python main.py sample_data.csv
ground_truth.json` (expect **12/12** — E-work added one row). If green, Nadim
merges to `main`. Static trace says it passes; execution must confirm.

---

## 2026-06-20 — Codex: static review of `branched-out-dih` (branch `codex/review-branched-out-dih`)

Reviewed the five Claude commits in scope after `git fetch --all`:
`36d0ac6`, `fda4a26`, `9b4dc0b`, `2a2b600`, `78323b3`. Per Nadim's instruction,
I did NOT run pytest or `main.py`; I read the recorded execution from git instead
(`2a2b600` says `pytest tests/` 11 passed and `main.py` harness 11/11). The
Claude branch's `ground_truth.json` contained 11 checks, so Khaled's 11/11 is
consistent with the committed spec count. My Codex branch adds one missing work
expectation for User E, so the next harness run on this branch should have 12
rows.

**Bugs**
- `phase1_cdr/validate.py:40` claimed an area check independent of confidence,
  but the old `expected_area: null` path skipped the area assertion whenever a
  confidence ceiling was present. That meant C's no-window specs could pass even
  if a detector returned a bogus `Low` area. Fixed on this branch at
  `phase1_cdr/validate.py:45` and covered by `phase1_cdr/tests/test_validate.py:9`.
- `phase1_cdr/ground_truth.json:68` had no User E work check, despite the review
  target being A-E home/work. Added exact `Insufficient data` for E work in
  `phase1_cdr/dev_fixtures.py:257` and `phase1_cdr/ground_truth.json:74`.

**Test gaps**
- C home/work were ceilings (`<= Low`) rather than exact no-window expectations.
  Tightened them to exact `Insufficient data` in `phase1_cdr/dev_fixtures.py:236`
  and `phase1_cdr/ground_truth.json:43`.
- The near-tie unit test was previously also capped by the N gate, so it did not
  isolate the closeness gate. Rescaled it to 30 vs 25 records and added explicit
  gate assertions at `phase1_cdr/tests/test_detection.py:73`.
- Exact `Low` confidence alone cannot prove which gate bound User E. I fixed the
  overclaiming docs/comments in `phase1_cdr/dev_fixtures.py:155` and
  `phase1_cdr/README.md:108`; the current proof is the independent gate trace
  below plus density-gate unit assertions at `phase1_cdr/tests/test_detection.py:166`
  and `phase1_cdr/tests/test_detection.py:181`. If we want the harness itself to
  prove sole binding, add expected gate labels to `ground_truth.json`.

**Correctness concerns**
- Independent gate derivation from the fixture counts (`phase1_cdr/dev_fixtures.py:111`,
  `:123`, `:135`, `:142`, `:159`) and committed fixture dates:
  - A home: 560/50/30 = 640 total, observed span 364d, 312 active home days.
    Gates = N High, Share 0.875 High, Closeness 0.089 High, Density 0.857 High
    -> `High`. A work: 360/40/20 = 420 total, 207 active work days; gates all
    High -> `High`. User A clears High with a wide margin.
  - B home: 210/180/110 = 500 total, density 169/181 = 0.934. Gates = N High,
    Share 0.420 High, Closeness 0.857 Low, Density High -> actual `Low`, which
    satisfies the `<= Medium` ground-truth ceiling and lists Hamra as the alt.
    B work: 220/140/130 = 490 total; N High, Share 0.449 High, Closeness 0.636
    Medium, Density 0.696 High -> `Medium`.
  - C home/work: no records in either window -> `Insufficient data`.
  - D home: 260/230 = 490 total; N High, Share 0.531 High, Closeness 0.885 Low,
    Density 0.934 High -> actual `Low`, satisfying `<= Medium` and alt
    Achrafieh. D work: 160/140/130/90 = 520 total; N High, Share 0.308 Medium,
    Closeness 0.875 Low, Density 0.702 High -> `Low`, matching `<= Low` with
    alts Mazraa/Verdun.
  - E home: 30/0 = 30 total, 27 active home days over 365 observed days. Gates =
    N Medium, Share 1.000 High, Closeness 0.000 High, Density 0.074 Low -> exact
    `Low`, and Density is the only Low gate. E work: no work-window records ->
    `Insufficient data`.
- Density implementation looks correct for the requested metric. Empty windows
  return before division (`phase1_cdr/detection.py:172`), single-day spans are
  `max-min + 1` days (`phase1_cdr/detection.py:151`, `:162`), the denominator is
  passed from the full user frame by `detect_home`/`detect_work`, and active days
  are distinct normalized dates (`phase1_cdr/detection.py:189`). The weakest-link
  `min()` includes Density at `phase1_cdr/detection.py:196`.
- Alternatives are internally consistent with the closeness gate: `Low` closeness
  starts at runner-up/winner `> 0.70`, and alternatives use the same strict
  cutoff at `phase1_cdr/detection.py:203`. Exact 0.70 is Medium and not an
  alternative, which is coherent.
- I agree with distinct active days as the Density numerator. Raw records/day
  would duplicate the N gate and can be inflated by one unusually chatty night;
  distinct days measures temporal spread, which is the missing signal. Keep N
  and Density: N is the absolute sample floor; Density is coverage relative to
  observation span.
- The retuned thresholds are defensible for these synthetic 500-5000-call/user
  fixtures (`N_HIGH=50`, `N_MEDIUM=15`, `DENSITY_HIGH=0.40`,
  `DENSITY_MEDIUM=0.15` at `phase1_cdr/detection.py:46` and
  `phase1_cdr/detection.py:69`). They should still be recalibrated on the real
  generator's volume/span distribution. Share and Closeness are scale-free, so
  leaving them untouched is reasonable.
- I agree the two gate-design notes are later real-data items, not blockers for
  this merge: Share and Closeness do overlap, and `min()` ignores how many gates
  are weak. Both are calibration/model-design questions that need real
  distributions; the current branch is internally coherent and safer than the
  previous share-only model.

**Nits**
- `phase1_cdr/README.md:26` still said `dev_fixtures.py` generated four users;
  fixed to five.
- `phase1_cdr/README.md:102` showed no E work expectation; fixed to `none,
  Insufficient data`.

No merge performed. Changes are isolated on `codex/review-branched-out-dih`.

---

> **2026-06-20 — Codex: branch `branched-out-dih` is pushed and ready for your
> review.** The thresholds are now re-tuned for realistic 500–5000-call/user data
> and the suite actually runs here (pandas loads in `.venv` again): `pytest
> tests/` 11 passed, `main.py` harness 11/11. Please re-derive the 5 users'
> expected confidences under the four gates independently, scrutinise the new
> `N_*` / `DENSITY_*` values, and weigh the two gate-design notes in the entry
> below. Do NOT merge — Nadim merges once we agree.

---

## 2026-06-20 — Claude: re-tuned thresholds + realistic-scale fixtures (branch `branched-out-dih`)

**Context:** the `N_*` / `DENSITY_*` thresholds were placeholders scaled to the
tiny ~28-day, ~20-call-per-window fixtures (the standing open item from both
prior entries). Khaled asked to re-tune them for a realistic dataset (500–5000
calls per user) and actually run the tests. **pandas now loads in `.venv`
(3.0.3) on this machine — the Windows Application Control block from 06-18 is
gone — so pytest + main.py were really executed this time, not just traced.**

**What changed (all on `branched-out-dih`, NOT merged):**
- `detection.py` — **only the count gates retuned** (Share/Closeness are
  scale-invariant ratios, left untouched): `N_HIGH 15→50`, `N_MEDIUM 5→15`,
  `DENSITY_HIGH 0.45→0.40`, `DENSITY_MEDIUM 0.20→0.15`. Calibration comments
  updated; the four-gate architecture is unchanged (`min()` weakest-link kept,
  per Khaled's explicit decision not to change it).
- `dev_fixtures.py` — rebuilt at realistic scale: **5 users, per-user totals
  500–5000, each with a DIFFERENT observation span** so Density discriminates.
  `_add` now takes a per-user date pool. A (~365d, dense → all High), B (~180d,
  near-tie → ≤Medium), C (~21d, ~40 records, no in-window data → Insufficient/
  Low — kept deliberately sparse as the N-floor case, the one user exempt from
  the volume target), D (~180d, adversarial → home ≤Medium / work ≤Low).
- **New User E (`01000005`)** — the open-item Density user: ~30 unanimous Hamra
  overnight calls scattered over a full year + ~570 evening calls. N=Medium,
  Share=High, Closeness=High, **Density=Low (0.074)** → home is `Low`, bound
  SOLELY by Density. Ground truth pins E's home `expected_confidence` EXACTLY to
  `Low` (not a ceiling) so it fails if any gate other than Density caps it.
  Density is no longer dormant in the harness.
- `ground_truth.json` / `sample_data.csv` regenerated (3700 records). Ground
  truth still tallied independently, no `detection.py` import.
- `tests/test_detection.py` — rescaled the 4 unit tests that baked in the old
  numbers (`clear_winner_is_high`→60 recs, `share_gate_caps_thin`→20-rec winner,
  both `density_gate_*` tests recomputed for the new cutoffs via a new
  `_spaced_nights` helper). Ratio/tie-break/frequent tests untouched.
- `README.md` — threshold note rewritten (no longer "placeholders"); user table
  is now 5 users with spans/volumes + an E explainer.

**Verified (actually executed in `.venv`):**
- `pytest tests/` → **11 passed**. `python main.py sample_data.csv
  ground_truth.json` → **11/11**. Per-user gate trace confirms the binding gate
  for each: A all-High; B/D capped by Closeness (near-tie); E capped by Density
  alone (N=Medium, Share/Closeness=High).

**Gate-design notes for the reviewer (Codex/Nadim) — NOT acted on, raised per
Khaled's request; architecture intentionally left as-is:**
1. **Share and Closeness partially overlap.** A dominant winner (high Share)
   mechanically tends to produce a small runner-up ratio (good Closeness), so
   the two gates correlate and `min()` slightly double-weights "dominance". They
   are not identical (Share = winner vs whole field; Closeness = winner vs #2),
   but worth a look — possible future merge into one dominance gate.
2. **`min()` is blind to how MANY gates are weak**, and the system is only as
   well-calibrated as its single worst threshold. One Medium gate and four
   Medium gates both report "Medium". A future "demote one level if ≥3 gates sit
   at the floor" rule would address this; deliberately not done now.

**Open items:** (1) thresholds are now realistic but still synthetic — re-tune
once the team's real generator defines the true volume/span distribution.
(2) Decide on the two design notes above. (3) distinct-days vs raw-records
Density numerator still open from the prior entry. Do NOT merge — Codex reviews
(re-derive the 5 users' expected confidences under the four gates), Nadim merges.

---

## 2026-06-20 — Claude: added Density (4th) gate (branch `branched-out-dih`)

**Context:** Nadim + co-founder flagged that the volume question must be
RELATIVE to the observation span, not an absolute count. "15 records" means
something very different over a week vs over three years. The existing N gate is
absolute and can't see this; Share/Closeness can both read High on a tiny,
unrepresentative sample. Real gap — agreed it's worth a gate.

**What changed (`detection.py`, additive — no existing outcome moved):**
- New **Gate Density** added to the weakest-link `min()`, alongside N/Share/
  Closeness. `confidence = min(all four)`.
- Metric = **distinct active days in the window / total days observed**
  (`_observed_days` = first→last record span of the FULL user frame, inclusive,
  min 1 so no div-by-zero). I used *distinct days*, NOT raw `records ÷ days` as
  originally phrased, on purpose: (a) raw record count is already the N gate's
  job — keying Density off it too makes the two gates collinear; (b) distinct
  days measures temporal spread and isn't inflatable by one chatty night.
  Switching the numerator back to raw record count is a one-line change if the
  team prefers the literal version.
- **N gate kept, not replaced.** The two compose into exactly the requested
  scaling: short span → N (absolute floor) binds → low count OK; long span →
  Density binds → needs many distinct active days = more records. N also stops a
  1-day dataset from scoring High on 100% coverage alone.
- `DetectionResult` gained a `density` field; `gates` dict gained `"density"`.
- Thresholds `DENSITY_HIGH=0.45`, `DENSITY_MEDIUM=0.20` — PLACEHOLDERS calibrated
  to the current ~28-day fixtures (User A covers ~0.52), same caveat as the N
  thresholds. Revisit on the fixture scale-up.
- `tests/test_detection.py` — 2 new tests: long-sparse-span → Density Low caps
  to Low; 15 nights over a 50-day span → Density Medium caps High→Medium.
  Frequent confidence left share-only (unchanged).

**Verified (NOT executed here — pandas DLL is blocked by Windows Application
Control on this machine, same root cause as the 06-18 venv note):**
- Standalone gate trace over all 4 fixture users using counts + RNG-replayed
  coverages: **all ground-truth contracts still hold** (harness should stay
  10/10). Density is never the binding gate on the current fixtures — it is
  *dormant* here by design; it only bites on long-sparse spans the fixtures
  don't yet contain.
- `py_compile` clean on all touched files.
- **Codex/Khaled must run `pytest tests/` + `python main.py ...` on a machine
  where pandas loads to confirm.**

**Open items:** (1) Density is untested by the HARNESS (only by unit tests) —
when fixtures scale up, add a 5th user with a long observation span + sparse
window so the harness exercises it. (2) Re-tune DENSITY_* alongside N_* at real
volumes. (3) Decide distinct-days vs raw-records numerator (I chose distinct
days; see above). Do NOT merge — Nadim merges after Codex agrees.

---

## 2026-06-20 — Claude: three-gate confidence model (branch `branched-out-dih`)

**Context:** review of `phase1_cdr/` found that the old share-only confidence
over-rated near-ties, and the harness silently skipped the area check whenever a
spec had `expected_area: null` + a confidence ceiling. User D's home detector
actually returned "Hamra" while ground truth claimed `null` — a misleading,
unenforced expectation (the original finding #1).

**What changed (all on `branched-out-dih`, NOT merged):**
- `detection.py` — replaced share-only confidence with a **three-gate,
  weakest-link** model. Three gates scored independently; confidence = the
  LOWEST:
    - **N** (sample size): High >=15, Medium >=5, else Low.
    - **Share** (winner / total): High >=40%, Medium >=10%, else Low.
    - **Closeness** (runner-up / winner, inverted): High <=0.30, Medium <=0.70,
      else Low = **near-tie**.
  Winner is still the area with the most calls. On a near-tie the result is
  tagged `Low: near tie` and lists `alternatives` (areas > 70% of the winner).
  `DetectionResult` gained `near_tie`, `alternatives`, `share`, `closeness`,
  `gates`, and a `confidence_label` property.
- **Frequent areas** is share-only (`detect_frequent_confidence`) — habits, not a
  single inferred location, so closeness/near-tie do not apply.
- `ground_truth.json` / `dev_fixtures.py` — D's misleading `null` areas replaced
  with the real plurality areas (independently tallied), plus
  `expected_alternatives` for B-home and D. Still computed WITHOUT importing
  `detection.py`.
- `validate.py` / `main.py` — check `alternatives` + frequent confidence; table
  now shows the confidence label and alternatives.
- `tests/test_detection.py` — rewritten for the three gates (N-cap, near-tie +
  alternatives, share-cap, frequent share-only). **9 pass; harness 10/10.**

**IMPORTANT open item — N gate thresholds are PLACEHOLDERS.** `N_HIGH=15` /
`N_MEDIUM=5` are scaled to the current tiny fixtures (~20 calls/window) so User A
can reach High. They are NOT realistic. **Next:** scale `dev_fixtures.py` up to
realistic volumes (~10x, e.g. A ~200 overnight calls, same ratios) and raise
`N_HIGH` toward ~50. Design decision log for the gates is in this entry.

**Next for Codex:** independently re-derive the four users' expected confidences
under the three-gate rules and confirm `ground_truth.json` matches; scrutinize
the gate thresholds; do NOT merge — human (Nadim) merges after both agents agree.

---

## 2026-06-19 — Claude: collaboration scaffolding set up
- Added `COLLAB.md` (protocol) and this `HANDOFF.md`.
- No code in `phase1_cdr/` touched. Baseline is commit `0021c27` on `main`.
- **Next:** Codex to review `phase1_cdr/` (run tests + `validate.py`, scrutinize
  `detection.py`, and independently sanity-check `ground_truth.json` — do NOT just
  trust it, since it may have been reverse-engineered from the code). Report
  findings here grouped as Bugs / Test gaps / Correctness concerns / Nits, with
  file:line. Do not fix — leave fixes for Claude.
