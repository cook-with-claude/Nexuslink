# Handoff Log

Shared scratchpad between Claude Code and Codex. Newest entries on top.
Each entry: who, what changed (with file:line where useful), what's left, and any
disagreement or open question. See `COLLAB.md` for the protocol.

## 2026-07-06 - Claude: Phase 3 increment 3.2b-1 (server master key + fail-closed lock) BUILT — FOR REVIEW

**Built, not merged.** Branch **`claude/phase3-3.2b-1-server-key`** (base `main`), subagent-driven per
the 3.2b-1 plan. Suite **208 passed / 1 skipped** (was 195), ruff clean, `git diff --stat main --
phase1_cdr/` empty (Phase 1 byte-frozen). Not merged — **Nadim merges** after Codex review. Next
increment = **3.2b-2** (multi-account `users` table, migration 2, `session["user_id"]`, retire
`auth.json`). ADR 0003 part 2 authored (3.2b-1 section).

**What shipped (the server-holds-key model):**
- **`app/infra/bootstrap.py` (INFRA leaf)** — a random 256-bit master key wrapped under a bootstrap
  passphrase in a gitignored keyfile `server.key` (`{kdf_salt,nonce,wrapped_key}` b64, `0600`
  best-effort). `unlock(passphrase)` generates+persists on first run, else unwraps; `BootstrapError` on
  empty/wrong passphrase or corrupt keyfile. Opens no DB, imports no Flask.
- **`main.py:resolve_and_unlock()`** unwraps at startup from `LP_BOOTSTRAP_PASSPHRASE` (env) →
  `getpass` console fallback into `app.config["DB_KEY"]`; on failure the server starts **LOCKED**
  (`DB_KEY=None`), never crashes.
- **Fail-closed lock gate** (`api.guards.install_lock_gate`): every `/api/*` route → **`503 LOCKED`**
  until `DB_KEY` is set, EXCEPT `/api/health` + `/api/status`. `/api/status` now returns `locked`
  alongside `account_exists`/`authenticated`.
- **Login/logout are session-only:** `_unlock` establishes the session identity but does NOT set
  `DB_KEY`; `_lock`/logout clear the session but do NOT clear the process-wide master key. `auth.json`
  now holds EXACTLY `{username,bcrypt_hash,created_at}` — no key material; `authenticate()` is
  bcrypt-only.
- **Behavior change:** `create_account` no longer builds the DB — it only writes `auth.json`; the
  encrypted `cdr.db` is built **lazily** by the first `get_db()` (migration seam, ADR 0002). So if the
  SETUP audit's lazy build fails, `/api/setup` returns 409 on retry but the account is recoverable via
  `/api/login`. The old "setup builds+cleans the DB, retryable" behavior + its test were intentionally
  removed. Fresh installs only (no `auth.json`→keyfile adapter; README documents the one-time
  `cdr.db`+`auth.json` reset).

**Commits (base `main`):** `de50af0`+`1eefb43` (bootstrap keyfile + corrupt-keyfile→BootstrapError) ·
`5515a76` (fixtures bootstrap-unlock the key) · **`57aba3f` (Tasks 3+4+5 BUNDLED into one
"server-holds-key model" commit** — the plan's 3-way split couldn't stay green per-commit because the
gate keys off `DB_KEY`, which only the routes-decouple stops nulling; splitting would have left an
intermediate red commit) · `f2117d4` (**fail-closed-test hardening** — an adversarial review found the
login/setup fail-closed tests **vacuous under `TESTING`**; rewrote them to drive the production 500
path, **mutation-proven** they now fail if the `_lock()`-on-audit-failure is removed) · `20d7fce`
(Task 6 startup unlock) · this docs commit (Task 7).

**Highest-risk edit (flag for Codex):** the fail-closed **semantics shift** — the guarantee moved from
"`DB_KEY is None` after a failed audit" to "**no session identity granted**" (login/setup/logout no
longer null `DB_KEY`). Verify no path leaves a session authenticated after a failed audit write, and
the lock gate can't be bypassed for any subject-data `/api/*` route. `lint-imports` runs WSL/CI only
(no grimp win_arm64 wheel) — `bootstrap` is in the Phase-1-forbidden set; no new layer violations.

## 2026-07-05 - Claude: Phase 3 increment 3.2b PLANNED (sub-split); build is NEXT SESSION (subagent-driven)

**Not built yet — planning only.** Branch **`claude/phase3-3.2b-1-server-key`** (renamed from
`...-server-key-users`), 4 doc commits, tip `0245369`. Suite still 195 (no code touched). **Next session:
execute the 3.2b-1 plan subagent-driven (fresh subagent per task, two-stage review, KEEP OPUS on
implementers — ★★★★★ carve-out, not a cheap build).**

**What happened this session (all decided + recorded; don't re-derive):**
1. **Prep docs refreshed** (`6556a0b`): `docs/reference/api.md` + `docs/phase3-surface.md` were stale
   (pre-3.2a auth shape) — fixed to post-3.2a (identity in `session["username"]`, `DB_KEY` the only
   process-global). This was Codex's non-blocking 3.2a follow-up. Re-grep confirmed no other drift.
2. **Brainstormed the 3.2b implementation forks** → recorded as **spec §14** (`77a94fd`, appended to
   `docs/superpowers/specs/2026-07-04-phase3-multiuser-platform-design.md`). Three decisions:
   - **Bootstrap unlock = `LP_BOOTSTRAP_PASSPHRASE` env → console `getpass` fallback.** No PyWebView
     dialog this increment (desktop documented as needing the env/console).
   - **Fresh installs only** — no `auth.json`→`users` legacy adapter (synthetic data; document a
     one-time reset of `cdr.db`+`auth.json`).
   - **3.2b sub-split into two branches** along the key-model / account-model fault line:
     **3.2b-1** = server master key + bootstrap unlock + fail-closed `503 LOCKED` + `/api/status.locked`
     (single-account `auth.json` login adapted so the password no longer unwraps the DB key; authors
     ADR 0003 **part 2**). **3.2b-2** = `users` table (migration 2) + multi-account bcrypt login +
     `session["user_id"]` + retire `auth.json` + `uninitialized`/`ready` status split (extends ADR pt2).
   - **Effort correction:** 3.2b is ★★★★★ = **max effort on the BUILD too** (Opus implementers, heavy
     Codex). The "plan-high/build-low" line belongs to **3.2a**, not 3.2b (I'd mis-said this; the
     difficulty memory was always right). Memory index fixed.
3. **Wrote the 3.2b-1 plan** (`0245369`):
   `docs/superpowers/plans/2026-07-05-phase3-3.2b-1-server-key.md` — 7 TDD tasks, ordered so the suite
   stays green at every commit: (1) `app/infra/bootstrap.py` keyfile init/unlock + INFRA-leaf guard +
   gitignore/import-linter; (2) test-harness `bootstrap_key` fixture across all integration fixtures
   (inert until task 4); (3) fail-closed lock gate + `status.locked`; (4) `account.py` drops the DB key
   (`auth.json` → `{username,bcrypt_hash,created_at}`, `authenticate` = bcrypt-only); (5) `auth/routes.py`
   login establishes a session WITHOUT unlocking + logout does NOT lock the server + rewrite the 3
   fail-closed tests (their guarantee moves from `DB_KEY is None` to "no session identity granted");
   (6) `main.py` startup unlock (env→getpass, serve locked on failure); (7) docs (ADR 0003 pt2 +
   api/surface/README/HANDOFF). Highest-risk edit = task 5 fail-closed semantics (flagged for Codex).

**Resume checklist next session:** `git checkout claude/phase3-3.2b-1-server-key` → open the 3.2b-1 plan
→ invoke **superpowers:subagent-driven-development** → execute task 1→7. `lint-imports` runs WSL/CI only
(no grimp win_arm64 wheel). Phase 1 byte-frozen. Not merged — Nadim merges.

## 2026-07-05 - Claude: Phase 3 increment 3.2a (identity de-globalization) ✅ MERGED to `main` (`0e90bdb`, pushed to origin)

**MERGED** with Nadim's explicit permission after **Codex CLEAR**: fast-forward `a17c4c2..0e90bdb`,
pushed to `origin/main`, branch `claude/phase3-3.2a-identity-deglobalization` deleted local + origin
(only `main` remains). 195 passed on merged main. Codex verified independently: `app/api/identity.py`
is a data-free SUPPORT leaf, `DB_KEY` never enters the session, auth gate intact, logout test deviation
sound; `lint-imports` 4 contracts kept (WSL), ruff clean, phase1 frozen. **Next pickup = increment 3.2b**
(server master key + multi-account `users` table, appends to ADR 0003 as part 2). Codex non-blocking
follow-up to fold into 3.2b: refresh `docs/reference/api.md` + `docs/phase3-surface.md` (still describe
the pre-3.2a auth shape). Details of the increment below.


Moved the operator username out of process-global `app.config["USERNAME"]` into a
new leaf SUPPORT module `app/api/identity.py` backed by the signed session cookie.
`api.guards.current_username()` swaps its body to delegate (ADR 0001 invariant 6);
the ~7 read-only call sites are **untouched**. `_unlock`/`_lock` write/clear the
session identity; the `USERNAME` config default is removed. **`DB_KEY` deliberately
stays process-global** (server master key, reinterpreted at bootstrap in 3.2b) —
only identity de-globalizes (spec §4.2, Codex #2/#3). Behavior-frozen for the
single-account desktop app (one session).

- New ADR `docs/adr/0003-server-key-and-identity.md` (accepted) — **part 1** of the
  server-key/auth decision; part 2 (server master key + `users` table) will *append*
  to this same ADR in 3.2b, no new number.
- New tests: `tests/phase2a/test_identity_context.py` (module round-trip + identity
  in session not config + cleared on logout) and `tests/architecture/` guard
  `test_identity_context_is_data_free` (no SQL, no `app.*` import — Codex #3). Of the
  three `config["USERNAME"]` fail-closed assertions in `test_transaction_semantics.py`,
  the login + setup cases re-point to a `session_transaction()` "no identity" check;
  the **audit-failure logout case keeps its `DB_KEY is None` + 401 assertions** (a
  session-cookie assertion can't hold there — under `TESTING` Flask discards the
  `session.clear()` mutation when the view raises, so `_lock()` still runs and the
  real gate is `DB_KEY`). `DB_KEY` assertions unchanged throughout. Suite **195
  passed** (was 191).
- Boundaries: `app.api.identity` added to the import-linter layers contract (bottom
  SUPPORT tier). `lint-imports` validated in CI/WSL only (no grimp win_arm64 wheel).
- Plan: `docs/superpowers/plans/2026-07-05-phase3-3.2a-identity-deglobalization.md`.
  Phase 1 byte-frozen. Next increment: 3.2b (server master key + multi-account
  `users` table, ADR 0003 part 2). Not merged — Nadim merges.

## 2026-07-05 - Claude: Phase 3 increment 3.1 (migrate-on-login) ✅ MERGED to `main` (`dd2857e`, pushed to origin)

**MERGED** with Nadim's explicit permission after Codex CLEAR: fast-forward `4d942b6..dd2857e`,
pushed to `origin/main`, branch `claude/phase3-3.1-migrate-on-login` deleted (only `main` remains).
191 passed on merged main. **Next pickup = increment 3.2a** (identity-accessor de-globalization,
ADR 0003 part 1) in a fresh session. Details of the increment below.


Wired `migrations.migrate(conn)` into `app/api/guards.py:get_db()` (after `storage.connect`,
before caching `g.db`; closes the conn if migrate raises). Activates ADR 0002's deferred flip —
**no new ADR minted** (0002 already documented this exact change); appended an "Activation"
note to `docs/adr/0002-db-migration-seam.md` instead. If Codex/Nadim want a standalone record,
the alternative was a new ADR 0005 — flagged in the plan.

- New tests: `tests/phase2a/test_migrate_on_login.py` — v0 auto-upgrade on login, no-op on a
  current DB (behavior-frozen), fail-closed on a too-new DB, and close-on-raise leak guard.
  Suite **191 passed** (was 187).
- Behavior-frozen for existing installs: every API test setups to `_LATEST`, so migrate is a
  no-op; invariant 2 intact (no commit on the up-to-date path). Phase 1 byte-frozen.
- **Internal SDD review done** (per-task + opus whole-branch): verdict **ready-to-merge**, no
  Critical/Important. Two Minors, both deferred (agree): (1) a `SchemaTooNewError`/`SchemaMismatchError`
  now reachable from any authed request falls to the global `INTERNAL` 500 handler — fine & fail-closed
  for 3.1 (no migration shipped yet, so only reachable via manual DB tamper/downgrade); tie a friendly
  "DB from newer app version" message to the FIRST shipped migration (3.2+). (2) close-on-raise leak
  guard now has a direct test (`test_get_db_closes_connection_when_migrate_raises`, added post-Codex
  at Nadim's request — Codex's prioritized suggestion); the drifted-v0 `SchemaMismatchError` path stays
  covered by the migration-runner tests + the shared `get_db()` except path. **Codex reviewed → CLEAR,
  no findings** (191 passed, ruff clean, phase1 empty).
- Branch commits (base `main` @ `4d942b6`): `070ac38` plan · `f3d77d8` code+tests · `f125182` docs ·
  ledger chore on tip. `git diff --stat main -- phase1_cdr/` empty. Suite 190 passed locally (py3.11.9).
- Plan: `docs/superpowers/plans/2026-07-05-phase3-3.1-migrate-on-login.md`. Next increment: 3.2a
  (identity-accessor de-globalization, ADR 0003 part 1). Not merged — Nadim merges.

## 2026-07-04 - Claude: SESSION CLOSE — Phase 3 DESIGN merged to main after 4 Codex rounds; pickup = plan 3.1

Phase 3 design is **fully brainstormed, Codex-reviewed (4 rounds), and MERGED to `main` (`040e3b6`)**.
Repo is a **single branch again** (`main`, in sync with `origin/main`); all Phase-3 review branches
pruned. **No code was written this session — the deliverable is the approved design.**

### What's on `main`
- **The spec (authoritative):** `docs/superpowers/specs/2026-07-04-phase3-multiuser-platform-design.md`
  — decision table, security-posture triage, data model (migrations), §2 increment plan (3.1→3.7),
  §4–§10 the auth/RBAC/approval/audit/TLS design, §11 testing, §12 risks, and **§13 the review log**
  (every Codex finding → its resolution across rounds 1–4). **Read §13 first next session** — it holds
  the corrections that aren't obvious from the body.
- `docs/phase3-surface.md` — corrected (the `DB_KEY` de-globalization premise was wrong; see its banner).
- CLAUDE.md Key-docs points at the spec; README Phase 3 row = "Planned — design approved".

### The decisions + the review corrections (so nothing is re-derived)
Scope = **real LAN multi-user server**, synthetic/portfolio framing. **Server holds the master key**
(manual bootstrap passphrase); **accounts in a `users` table inside the encrypted DB**; **browser
clients** (desktop shell stays single-user localhost → packaging stays deferred); **admin/analyst**
RBAC; **dataset-access approval only**; **comprehensive tamper-evident activity log** (every operator
intent). Non-obvious corrections from review, now in the spec:
- **`DB_KEY` stays process-global** as the *server* master key — NOT per-session. Only *identity*
  de-globalizes (3.2a swaps `current_username()` to a **data-free SUPPORT** context; no DB read; no
  `current_role` yet).
- **Access predicate lives in a shared `app/authz/` module at the AUDIT tier** — imported only by
  APPLICATION routes, applied as decorators (`require_role`/`require_active`/`require_dataset_access`),
  **excluded from the independence set**, NOT SUPPORT, NOT a peer domain. `api.guards` stays data-free.
  The DB-backed `authz.current_role()`/`current_username()` arrive with multi-account (3.2b/3.3).
- **Logged routes open their unit-of-work `BEGIN IMMEDIATE` up front**; `write_audit` is INSERT-only
  (invariant 2 intact). **Live role/disabled read per request via `authz`**; cookie carries `user_id`
  only. **Bootstrap fail-closed** (503 until unlock; first-admin bound to localhost). Access
  enforcement covers ALL subject-data paths; `403`≡`404`. **`DATASET_OPENED` server-enforced**.
  Failed-login → encrypted chained log post-unlock. Trusted-proxy CIDR + `SESSION_COOKIE_SECURE`.
  Internal-service mTLS = **N/A** (monolith). TOTP MFA = late/optional (3.7).

### NEXT SESSION — exact pickup
1. **Invoke `writing-plans` scoped to increment 3.1 ONLY** — wire `migrations.migrate(g.db)` into
   `app/api/guards.py:get_db()` (right after `storage.connect`), author **ADR 0002**. Tiny, mechanical,
   independent of everything the review debated. Then build → Codex review → Nadim merges, per increment.
2. Increments after 3.1 (each its own plan→build→review→merge): 3.2a (identity de-globalization,
   behavior-frozen) · 3.2b (server key + multi-account, ADR 0003) · 3.2c (network + TLS) · 3.3 (RBAC +
   `app/authz/`) · 3.4 (owner dim + approval, ADR 0004) · 3.5a/3.5b (activity capture / hash chain) ·
   3.6 (UI) · 3.7 (TOTP MFA).
3. **Before coding 3.2b**, re-grep the `phase3-surface.md` inventory in case anything drifted.
4. Auto-memory `phase3-design-decisions` carries this same summary for cold-start recall.

### Backlog (unchanged, non-blocking)
GitHub #14/#17 (UI polish), leftover #16 bits, methodology #2/#7/#8/#9 (mostly gated behind frozen Phase 1).

## 2026-07-04 - Claude: Phase 3 spec — round-4 patch (Codex #4 accessor-wording closed) on `claude/phase3-spec-patches` - FOR REVIEW

Codex round 4 (`codex/phase3-design-review`, `cc28b36`): the `authz` AUDIT-tier fix holds and the
illegal `guards → authz` edge is gone, but **#4 STILL-PARTIAL** for a residual **wording** carryover
— §2 3.2a and §4.2 still called `current_username()`/`current_role()` SUPPORT accessors "resolving
from the users row," contradicting §5/§10 (those DB-backed accessors are `authz`). It could send an
implementer toward a SUPPORT DB read. Not a design flaw — the design was already right in §5/§10;
the earlier prose just lagged. Fixed on the same branch. Design-only, Phase 1 frozen.

### The fix (accessor phasing made explicit)
- **3.2a** swaps only `current_username()` to read the **data-free SUPPORT identity context**
  (single-account, no DB → behavior-frozen). **`current_role` is NOT introduced in 3.2a** (no roles
  until multi-account).
- The **DB-backed** live `authz.current_role()`/`authz.current_username()` arrive with multi-account
  (3.2b/3.3) in the **`authz` tier**; a SUPPORT module never reads the DB. §2 3.2a + §4.2 rewritten;
  §13 gains a "Review round 4" subsection. Grep confirms no remaining "resolve from the users row"
  in a SUPPORT context.

### Verification
- Design/docs only. `git diff --stat main -- phase1_cdr/` empty; fences paired. No tests (design review).

### For Codex/Nadim
- Diff since round 3 = `git diff dffd2d4..claude/phase3-spec-patches` (two prose edits + §13 note).
  This was the last open thread: **all 12 findings + both pushbacks closed across 4 rounds.** If
  Codex concurs, the full 3.2+ design is ready. Not merged — Nadim merges.

## 2026-07-04 - Claude: Phase 3 spec — round-3 patch (Codex #4 layer edge closed) on `claude/phase3-spec-patches` - FOR REVIEW

Codex round 3 (`codex/phase3-design-review`, `ec74add`): **#2 and #9 RESOLVED**, **#4 STILL-PARTIAL**
for one real reason — the round-2 `authz` design was self-contradictory. I said `authz` is "peer to
`audit`" **and** that `api.guards` imports it; but `audit` sits **above** SUPPORT in the layer order,
so `api.guards (SUPPORT) → authz` is an illegal **upward** import. Codex is right; fixed on the same
branch. Design-only, Phase 1 frozen.

### The fix (authz layer pinned; the SUPPORT→authz edge removed)
- **`authz` placed at the AUDIT tier:** `APPLICATION → DOMAIN/DATA → {audit, authz} → SUPPORT →
  INFRA`. Imported **only by APPLICATION `<domain>.routes`** (downward, exactly like `audit`);
  imports only `api.responses` (SUPPORT) + `infra`; excluded from independence. `authz/repo` reads
  its facts via `conn`+`infra` (like `audit` writes its table) — no DOMAIN/DATA import.
- **No `api.guards → authz` edge.** The data-reading checks are **`authz` decorators the routes
  apply** — `@authz.require_role` / `@authz.require_active` (live role/disabled) /
  `@authz.require_dataset_access`. `api.guards` (SUPPORT) keeps only the **data-free**
  `login_required` (session `user_id` + server-unlocked) + content-type guard + `get_db`. Live
  `current_role()`/`current_username()` are `authz` accessors. Added a `tests/architecture/` assertion:
  no `api.* → app.authz` import.
- **Denial-audit ownership pinned:** the `authz` decorator returns the 403 signal; the **route/error
  handler** writes the audit row via `audit` (APPLICATION→audit), so `authz` needs no `audit` import.
- Stale §3 "SUPPORT policy module" sentence corrected. Sections updated: §2 (3.3/3.4), §3, §4.4, §5,
  §10, §13 (new "Review round 3" subsection).

### Verification
- Design/docs only. `git diff --stat main -- phase1_cdr/` empty; code fences paired (4). Grepped: the
  only remaining `peer to audit` / `guards imports authz` strings are historical text describing the
  rejected round-2 shape while explaining the fix — no live stale claim.
- No tests (design review).

### For Codex/Nadim
- Diff since round 2 = `git diff e66fbab..claude/phase3-spec-patches`. All 12 findings + both
  pushbacks are now closed and the design is internally consistent under the CI-enforced contracts.
  If Codex concurs, **the full 3.2+ design is ready** (3.1 was always independent). Not merged — Nadim merges.

## 2026-07-04 - Claude: Phase 3 spec — round-2 patches (Codex #2/#4/#9 PARTIALs closed) on `claude/phase3-spec-patches` - FOR REVIEW

Codex's round-2 review (`codex/phase3-design-review`, `5def70f`) confirmed 9/12 findings RESOLVED
and flagged **#2, #4, #9** as PARTIAL. Verified each; all three were legit implementation-altitude
gaps, now closed on the **same** `claude/phase3-spec-patches` branch (appended commit). Still
**design-only, no code, Phase 1 frozen.**

- **#2 — `phase3-surface.md` stale body bullets:** the correction banner was there, but the
  "intended seam" + "Phase 3 change plan" bullets still said `get_db` de-globalizes the key / remove
  the `DB_KEY` default. Rewrote both to the corrected model (`DB_KEY` = server master key, not
  per-session; only identity → `app/api/identity.py`).
- **#4 — access-predicate module shape:** `api/policy.py` (SUPPORT) reading via a repo would import
  upward (SUPPORT→DATA) or run its own SQL. Replaced with a shared **`app/authz/`** module modeled on
  `audit` — `authz/repo` (facts), `authz/policy` (pure decision), `authz/__init__` (require_* → 403);
  added to the import-linter **layers** contract + **excluded from independence** (like `audit`), so
  every domain's routes may call it with no domain→domain edge and no SUPPORT-upward import. §4.4's
  live role/disabled read also routes through `authz/repo`, keeping SUPPORT guards data-free.
- **#9 — hash-chain transaction composition:** `BEGIN IMMEDIATE` inside `write_audit` would nest in
  the route's open transaction. Pinned the recipe: the **route** opens its UoW `BEGIN IMMEDIATE` up
  front for logged routes; `write_audit` is **INSERT-only** (no begin/commit/rollback) — invariant 2
  intact. `infra.storage.begin_immediate(conn)` exposes the opt-in.
- Doc nit: removed the stray trailing ``` fence Codex noted (pre-existing).

Spec §13 now has a "Review round 2" subsection recording all three closures. Sections touched:
spec §2, §4.2/§4.4, §5, §6, §7.3, §10, §13 + `phase3-surface.md` seam/change-plan.

### Verification
- Design/docs only. `git diff --stat main -- phase1_cdr/` empty. Grepped: no *live* `api.policy`
  refs (the 2 remaining name the rejected draft while explaining the fix); code fences paired.
- No tests (design review).

### For Codex/Nadim
- Round-3 diff = `git diff main...claude/phase3-spec-patches` (now includes the round-2 edits).
  If Codex is satisfied, **all three PARTIALs are closed → clear to plan 3.1 and then 3.2+**.
  Not merged — Nadim merges.

## 2026-07-04 - Claude: Phase 3 spec PATCHED for Codex review round 1 on `claude/phase3-spec-patches` - FOR REVIEW

Codex reviewed the merged Phase 3 design spec (on `codex/phase3-design-review`, `92b667d`) —
verdict **sound direction, patch before planning 3.2+**. Twelve required changes + two smaller
pushbacks. I verified each against the current code model (single-account login derives the raw
SQLCipher key from the password; `config` globals; `/api/status` = `{account_exists,authenticated}`;
independence contract names whole domain packages) and **accepted all of them** — several fix real
flaws, not nits. Spec patched on this branch; `phase3-surface.md` corrected too. **Design-only, no
code, Phase 1 frozen.**

### What changed in the spec (see the new §13 resolution table for the full map)
- **DB-key premise corrected (Codex #2, the big one):** 3.2a narrowed to **identity accessors
  only**; `DB_KEY` **stays process-global** and is reinterpreted as the *server* master key (there is
  **no per-session DB key** under server-holds-key). `phase3-surface.md` got a correction banner.
- **Layering (Codex #3, #4):** per-session identity context → `app/api/identity.py` (SUPPORT, not
  `auth` DOMAIN); the dataset-access **predicate** → neutral `app/api/policy.py` (SUPPORT), NOT the
  `app/access` domain (which keeps only the request/decide workflow) — avoids an independence-contract
  violation.
- **Bootstrap fail-closed (Codex #1):** `503`/locked until master-key unlock; `/api/status` =
  locked|uninitialized|ready; first-admin bound to localhost (no public LAN `/api/setup` race).
- **Access coverage widened (Codex #5):** gate/filter records, targets, results, exports, phone
  pickers, and `target_id` resolution — not just dataset+analysis; `403`≡`404`.
- **`DATASET_OPENED` server-enforced (Codex #6):** emitted server-side, deduped per (session,dataset),
  so a direct-API `GET /records` still logs.
- **Failed-login contradiction fixed (Codex #7):** operator `LOGIN_FAILED` → encrypted chained log
  post-unlock; sidecar only pre-unlock.
- **Live session authority (Codex #8):** cookie carries `user_id` only; role/disabled read live per
  request — disabling/re-roling revokes stale sessions.
- **Hash-chain concurrency (Codex #9):** serialized append (`BEGIN IMMEDIATE`/`chain_head`); UI says
  "stored log verifies," not "history complete" (tail-truncation caveat).
- **Trusted-proxy (Codex #10):** `X-Forwarded-*` trusted only from a configured CIDR;
  `SESSION_COOKIE_SECURE` in HTTPS mode.
- **Sequencing (Codex #11):** access predicate moves to 3.4 (with its schema); 3.3 = role guard only.
- **`/api/status` semantics (Codex #12)** + **cert hot-reload downgraded** to a documented
  restart/reload procedure (smaller pushback).

### Verification
- Design/docs only. `git diff --stat main -- phase1_cdr/` empty. No code, no tests run (spec review).
- Spec self-consistency grepped: no stale `auth/session.py`, no per-session `DB_KEY`, no
  `user_id + role` cookie claim contradicting the live-role model.

### For Codex/Nadim
- Diff to review = `git diff main...claude/phase3-spec-patches` (spec + `phase3-surface.md` + this
  entry). Not merged — Nadim merges. If Codex is satisfied, **next step is writing-plans for 3.1**
  (unchanged and independent); do NOT plan 3.2+ until this patched design is accepted.

## 2026-07-04 - Claude: PHASE 3 DESIGN brainstormed + spec committed (NOT merged) — pickup = write plan for 3.1

Full brainstorming session on Phase 3 with Nadim. **No code, no implementation** — the deliverable is
an approved design spec. Nadim explicitly stopped before plan-writing so next session resumes with all
decisions already made.

### Where it lives
- Branch **`claude/phase3-design`** (commits `bc535d9` spec, `077b836` security/split updates, + this
  bookkeeping commit). **NOT merged to `main`.** `main` unchanged (`143a551`).
- The design: **`docs/superpowers/specs/2026-07-04-phase3-multiuser-platform-design.md`** — read it first;
  it has the full decision table (16 rows), security-posture triage, increment plan, data model, and risks.
- **Pickup decision for Nadim:** either merge the spec branch to `main` first, or next session works on
  `claude/phase3-design` directly. Nothing depends on it being on main except discoverability.

### Decisions locked this session (see spec §1 for the authoritative table)
1. **Scope:** real **LAN multi-user server** (synthetic-data/portfolio framing — accountability demo, not
   surveillance; keeps the CLAUDE.md hard rule satisfied). Resolves the long-open LAN shared-vs-independent
   fork → **shared**.
2. **Key/trust model:** **server holds the master key** in memory, unlocked at server start by a **manual
   admin bootstrap passphrase** (never stored unwrapped). Accounts become a **`users` table inside the
   encrypted DB** (replaces per-user `auth.json`).
3. **Clients:** **browsers → LAN server**. Desktop PyWebView shell stays a single-user localhost
   convenience → the deferred packaging/distribution work **stays deferred**.
4. **Roles:** admin / analyst (least-privilege, deny-by-default). Admin imports+owns datasets.
5. **Approval gate:** **dataset-access only** (no per-query approval).
6. **Activity log:** **every operator query/intent logged** (actor/action/dataset/subject/params/result),
   admin-reviewable per operator. Loggable reads become **POST intents** (avoids the HEAD/prefetch phantom
   rows — the export-endpoint lesson). Records browsing = one `DATASET_OPENED` event, not per page.
7. **Tamper-evidence:** hash-chained audit + append-only triggers, built, with an **honest threat model**
   (detects naive edits/ordering; NOT proof against a key-holder unless externally anchored = design-only).
8. **Transport:** HTTPS **min TLS 1.3**, internal-CA certs, renewal, reverse-proxy-compatible.
9. **MFA:** **TOTP built** as a late/non-blocking increment (3.7); client-cert mTLS documented as the PKI
   alternative.
10. **Security triage** of Nadim's enterprise checklist done (spec §1 posture map). Honest pushback: **mTLS
    between "internal services" is N/A** — this is a modular monolith, no service hop; design-only if ever
    decomposed. Reverse proxy / firewall / segmentation / monitoring / KMS = operating-model, documented not coded.

### Increment plan (small steps, per Nadim's preference — spec §2)
3.1 migrate-on-login wiring (ADR 0002) · 3.2a de-globalization (behavior-frozen) · 3.2b multi-account+server
key (ADR 0003) · 3.2c network+TLS baseline · 3.3 RBAC guards · 3.4 owner dim + dataset-access approval
(ADR 0004) · 3.5a activity capture · 3.5b tamper-evidence · 3.6 UI (may split per screen) · 3.7 TOTP MFA.

### Next session (pickup)
1. (Optional) Nadim merges `claude/phase3-design` to `main`.
2. Invoke **writing-plans** scoped to **increment 3.1 ONLY** (tiny: wire `migrations.migrate(g.db)` into
   `api/guards.py:get_db()`, author ADR 0002). Then build → Codex review → merge, per increment.
3. Before coding 3.2b: re-grep the `phase3-surface.md` inventory in case anything drifted.

## 2026-07-04 - Claude: SESSION CLOSE — #10, README 2C, #16 all merged; native testing restored

Everything this session is **landed on `main`** (`143a551`); the repo is a single branch again.

### What landed on `main` (d74dce7 → 143a551, all Codex-CLEAR, all pruned)
1. **#10 weak-gate surfacing** (`2e2d00c`) — binding-gate + weak-gate-count caption under Home/Work
   cards (`bindingGates`/`bindingNote` in `components.js`). Plus the **first frontend behavioural
   test** (`components.test.mjs`, Node's built-in `node --test`, wired into the CI `frontend` job).
2. **README 2C → "Complete — merged"** (`8549b4c`) — the durable half of last session's dangling
   `445e9dd`, re-applied README-only; stale HANDOFF half discarded; `claude/session-close` deleted.
3. **#16 dedup detection renderer** (`143a551`) — shared `detectionBlock`/`frequentAreasBlock`/`pct`
   in `components.js`; `results.js` + `spreadsheet.js` both call them (only wrapper class differs).
   Codex fixed one stale gate: `test_ui.py` needle `confidencePill` → `resultsScreen`.

### Verified end state
- **187 passed** — now runs **natively** on Windows (`.venv` py3.11.9, pandas 3.0.3; the old Smart
  App Control block is gone), AND Codex's WSL run. `node --test` 10/10. ruff clean, import-linter 4
  kept. `git diff --stat main -- phase1_cdr/` empty (Phase 1 frozen).
- CLAUDE.md refreshed: frontend-test commands + the "grep `tests/` on JS symbol renames" caveat +
  the native-testing update.

### Open / next
- **Nothing in flight.** No branches pending review.
- **Phase 3** is the next move (first: wire `migrations.migrate(g.db)` into `app/api/guards.py:get_db()`,
  ADR 0002, then auth de-globalization per `docs/phase3-surface.md`).
- Backlog (non-blocking): GitHub **#14/#17** (skippable portfolio-gloss on UI-unreachable edges),
  the remaining low-value #16 bits (`downloadResultsXlsx` vs `request()`, field helper), and
  methodology **#2/#7/#8/#9** (mostly gated behind frozen Phase 1).

## 2026-07-04 - Codex: review of detection-renderer dedup on `codex/dedup-detection-renderer-review` - CLEAR after test fix

Reviewed `origin/claude/dedup-detection-renderer` at `fcb4507` against `main`
(`8549b4c`). Verdict: **CLEAR after one test-only fix**. The renderer refactor itself is
behaviour-equivalent; I found no runtime/frontend defect in the extraction. This branch
fast-forwards the Codex review branch to Claude's tip, then adds the stale smoke-test fix
below plus this verdict. Nadim still merges to `main`.

### Review notes
- `detectionBlock()` matches both former copies: child order stays `card-head` ->
  `result-area` -> optional `bindingNote` -> alternatives -> `gateTrace`, and the area
  fallback remains `(r && r.area) ? r.area : "—"`. Results uses the default `.card`;
  Spreadsheet passes `.det-block`.
- `frequentAreasBlock()` is equivalent for `null`, `undefined`, and empty arrays. The old
  Spreadsheet copy normalized `payload.frequent_areas || []`; the shared helper's
  `!areas || areas.length === 0` guard reaches the same empty branch for those values, then
  preserves note/table order for ranked rows.
- Removed imports/local helpers have no stale screen references: `confidencePill`,
  `gateTrace`, `bindingNote`, `sampleNote`, and local `pct()` are now used through
  `components.js` only where appropriate.
- No naming collision: Spreadsheet's `detectionCard(datasets)` controller is still separate
  and untouched. The `result-area mono` at `spreadsheet.js:468` is the frequency-explorer
  tally winner line, not a third detection-card copy.
- Scope is right for #16: only the duplicated detection/frequent-areas renderers were
  extracted. The lower-value `downloadResultsXlsx` vs `request()` and field-helper cleanup
  items were left alone.

### Fix made by Codex
- `tests/phase2a/test_ui.py`: the static asset smoke test still looked for
  `confidencePill` inside `/js/screens/results.js`. That was only a route-serving needle,
  and the refactor correctly moved the literal out of the screen module, so WSL pytest
  failed 186/187 before the fix. I changed the needle to `resultsScreen`, preserving the
  test's purpose without coupling it to a removed implementation detail.

### Verification
- Native Node: `node --check app/web/js/components.js`,
  `node --check app/web/js/screens/results.js`,
  `node --check app/web/js/screens/spreadsheet.js` -> clean.
- Native Node: `node --test app/web/js/components.test.mjs` -> **10 passed**.
- WSL `/root/lp-venv`: `pytest tests/phase2a tests/architecture phase1_cdr/tests` ->
  **187 passed** after the smoke-test fix.
- WSL `/root/lp-venv`: `ruff check app tests main.py` -> clean.
- WSL `/root/lp-venv`: `lint-imports` -> 4 contracts KEPT.
- `git diff --stat main -- phase1_cdr/` -> empty after restoring the known `/mnt/c`
  line-ending churn in `phase1_cdr/ground_truth.json` and `phase1_cdr/sample_data.csv`.

## 2026-07-04 - Claude: GitHub #16 — dedup the detection renderer on `claude/dedup-detection-renderer` - FOR REVIEW

The home/work detection card and the frequent-areas card were copy-pasted between
`results.js` and `spreadsheet.js`, differing ONLY by the wrapper class (`.card` vs
`.det-block`). That is a live drift risk (the two panels could silently show different
things for the same subscriber) and a real maintenance tax — #10 had to be applied to
both copies identically. This extracts one source of truth. Based cleanly on `main`
(`8549b4c`, i.e. post-#10). **Presentation only — Phase 1 untouched.**

### Change (frontend only)
- `app/web/js/components.js`: new shared `detectionBlock(title, r, wrapClass="card")`,
  `frequentAreasBlock(areas, conf, wrapClass="card")`, and `pct()` (was duplicated in both
  screens). Behaviour-identical to the two former copies; `wrapClass` is the only thing that
  ever differed.
- `screens/results.js`: uses them (default `"card"`); drops local `detectionCard`,
  `frequentAreasCard`, `pct`. `frequentContactsCard` stays (Results-only, not duplicated).
- `screens/spreadsheet.js`: uses them with `"det-block"`; `renderDetection` shrinks to three
  calls; drops the inline `block()` and the duplicate `pct`. The unrelated `detectionCard(datasets)`
  controller (L254) is a different function — untouched, no collision.
- `components.test.mjs`: +3 smoke tests locking the wrapper-class param + card content so the
  two screens can't drift again (10 tests total).

### Deliberately scoped
Only the duplicated detection/frequent-areas renderers. The lower-value #16 items
(`downloadResultsXlsx` vs `request()`, the field helper) are left alone.

### Verification
- `node --check` clean on all 3 JS files; `node --test app/web/js/components.test.mjs` → **10 passed**.
- No dangling refs to the removed symbols in either screen (no runtime ReferenceError); every
  retained/added import is used. Net −11 lines of app code.
- No Python touched → **187 pytest unaffected**; `git diff --stat main -- phase1_cdr/` empty.
- Self-review (high-effort, all 8 angles): behaviour-equivalence to both originals confirmed
  structurally; no correctness findings.

### For Codex/Nadim
- Review focus: is the shared version truly byte-equivalent to BOTH former copies (child order,
  the `!areas` empty guard vs the old `payload.frequent_areas || []`, the `(r && r.area)` guard)?
  And confirm no third detection-card copy was left un-deduped (`renderTally`'s `result-area mono`
  at `spreadsheet.js:468` is a tally winner line, intentionally NOT a detection card).
- Not merged — Nadim merges. Independent of everything else.

## 2026-07-04 - Codex: review of weak-gate surfacing on `codex/weak-gate-surfacing-review` - CLEAR

Reviewed `origin/claude/weak-gate-surfacing` at `5823a1d` against `main` (`d74dce7`).
Verdict: **CLEAR**. I made no code fixes. This branch fast-forwards the Codex review branch
to Claude's tip, then records this verdict; Nadim still merges to `main`.

### Review notes
- The phrasing is honest for the current model: `bindingNote()` says what holds the raw
  weakest-link level down, without inventing a second threshold (`app/web/js/components.js:163`,
  `app/web/js/components.js:175`). The short names also line up with the fuller gate-trace labels:
  sample size/N, dominance/share, separation/closeness, and coverage/density
  (`app/web/js/components.js:105`, `app/web/js/components.js:152`).
- Suppressing High is correct for home/work. Phase 1 returns no gates for an empty window, and for
  non-empty windows computes `confidence = min([gate_n, gate_share, gate_closeness, gate_density])`
  before serializing all four gates (`phase1_cdr/detection.py:196`, `phase1_cdr/detection.py:219`,
  `phase1_cdr/detection.py:240`). So `confidence === "High"` means all four home/work gates are
  High; there is no binding weakness to surface.
- The "headline not among the gates" guard is unreachable for real home/work payloads: the backend
  serializes raw `confidence` separately from `confidence_label` (`app/analysis/bridge.py:36`,
  `app/analysis/bridge.py:37`), so near-tie labels do not interfere with matching gate values.
- No XSS regression: `bindingNote()` passes plain text through `el()`, whose string-child path uses
  `document.createTextNode()` and has no `innerHTML` sink (`app/web/js/components.js:18`).
- The render sites are scoped to Home/Work detection cards on both Results and Spreadsheet
  (`app/web/js/screens/results.js:77`, `app/web/js/screens/spreadsheet.js:338`), not to the
  single-gate frequent-areas confidence object.
- Pushback on the self-review note: with the current branch order, a single present gate would render
  "one gate", not "all 1 gates". It still should remain unwired from frequent areas because that card
  intentionally has no gated verdict.
- The new frontend test is sane for the no-build SPA: it imports the real component module, uses only
  `node:test`/`node:assert`, and stubs the minimal DOM surface needed by `el()`
  (`app/web/js/components.test.mjs:15`). CI invokes it by explicit file path
  (`.github/workflows/ci.yml:99`).

### Verification
- Native Node: `node --check app/web/js/components.js`,
  `node --check app/web/js/screens/results.js`,
  `node --check app/web/js/screens/spreadsheet.js` -> clean.
- Native Node: `node --test app/web/js/components.test.mjs` -> **7 passed**.
- WSL `/root/lp-venv`: `pytest tests/phase2a tests/architecture phase1_cdr/tests` -> **187 passed**.
- WSL `/root/lp-venv`: `ruff check app tests main.py` -> clean.
- WSL `/root/lp-venv`: `lint-imports` -> 4 contracts KEPT.
- `git diff --stat main -- phase1_cdr/` -> empty after restoring the known `/mnt/c` line-ending churn
  in `phase1_cdr/ground_truth.json` and `phase1_cdr/sample_data.csv`.

## 2026-07-03 - Claude: SESSION CLOSE — #10 pushed FOR REVIEW; pickup checklist

Session wrap-up. One feature in flight (GitHub #10), pushed to origin, awaiting Codex review.

### Branch state
- **`origin/claude/weak-gate-surfacing`** (`139354e`, based on `main` `d74dce7`) — GitHub #10
  (binding-gate + weak-gate-count caption). Presentation-only, Phase 1 frozen, 187 green,
  real-app screenshots done. Full detail in the entry directly below.
- **`main`** = `d74dce7` (unchanged this session).
- **`claude/session-close`** = `445e9dd` — LAST session's bookkeeping commit (HANDOFF/README:
  2C→"Complete" flip), **still unmerged to main**. Not touched this session so the #10 diff stays clean.

### Pickup checklist for next session (before Nadim merges #10)
1. **Codex reviews** `origin/claude/weak-gate-surfacing` (diff = `git diff main...origin/claude/weak-gate-surfacing`,
   4 src files + HANDOFF). Review focus: the "Held at {level} by …" phrasing + the suppress-on-High call.
2. Apply any Codex fixes on the same branch; re-run WSL suite (should stay 187) + `node --check`.
3. **Nadim merges #10** (fast-forward `main`), prune the branch.
4. **Decide `445e9dd`**: fold last session's bookkeeping into `main` (or discard) — it's the only
   other unmerged ref. If merged, the README 2C row goes to "Complete" on `main`.
5. Still open, non-blocking: GitHub **#14–#17** (spreadsheet polish; #14+#17 are the cheap pair),
   and the methodology cluster **#2/#7/#8/#9** (mostly gated behind frozen Phase 1 / real-data calibration).
6. **Phase 3** still parked (first move: wire `migrations.migrate(g.db)` into `app/api/guards.py:get_db()`).

## 2026-07-03 - Claude: GitHub #10 — surface binding gate(s) + weak-gate count on `claude/weak-gate-surfacing` - FOR REVIEW

Implements GitHub issue #10 (refines #2): the headline confidence is `min()` across the
four gates, so it discards **how many** gates sit at the floor — "one Low, three High" (a single
fixable weakness) and "all four Low" (hopeless) both render as just "Low". This surfaces the
**binding gate(s)** + their count as a caption under each Home/Work result. **Presentation only —
Phase 1 is untouched; `gates` was already serialized at `app/analysis/bridge.py:45`.** Branch is
based cleanly on `main` (d74dce7).

### Change (frontend only)
- `app/web/js/components.js`: new shared `bindingGates(result)` + `bindingNote(result)`. `bindingGates`
  returns the gate keys equal to the headline level (the min), or `null` when the notion doesn't
  apply — **suppressed on High** (all gates High, nothing caps it), on an empty window (`gates` is
  null → "Insufficient data"), and on tallies (no 4-gate dict). Wording: one gate →
  "Held at {level} by one gate: {name}."; partial → "…by N of 4 gates: …"; all → "…by all 4 gates: …".
  Gate short-names: N→sample size, share→dominance, closeness→separation, density→coverage. **No
  invented severity color** — plain text carries the gradient, consistent with the sample-size note.
- `app/web/js/screens/results.js` + `screens/spreadsheet.js`: render `bindingNote(r)` under the
  result area (above alternatives / gate trace) on both detection cards.
- `app/web/css/app.css`: `.binding-note` — a subtle left-border caption (annotation, not a competing pill).

### Deliberately NOT done
- No new severity pill/color or invented "N gates weak" threshold (same discipline as the removed
  frequent-areas pill). The `min()` floor itself is unchanged — this only stops discarding the gate
  vector at the surface. Export (`analysis/export.py`) not touched — could gain a binding-gate column later.

### Verification
- Logic smoke test (DOM-stubbed import of the real `components.js`): one/partial/all wording correct;
  High + empty-window + tally all suppressed. `node --check` clean on all 3 JS files.
- **187 pytest passed** (WSL `/root/lp-venv`, unchanged — no Python touched). `git diff --stat main --
  phase1_cdr/` empty.
- **Live real-app screenshots** (headless Windows Chrome over CDP, seeded through the real
  setup→import→analyze pipeline in WSL): Sub 02 → Home "Held at Low by one gate: separation." +
  Work "Held at Medium by one gate: separation." (two levels, single binding gate each); Sub 05 →
  Home "Held at Low by one gate: coverage.", Work "Insufficient data" with the note correctly absent.

### For Codex/Nadim
- Pure display addition; review the framing (is "Held at {level} by …" the right honest phrasing, and
  is suppress-on-High correct?). Not merged — Nadim merges. Independent of issues #14–#17.
- **Loose end (not mine to fix unprompted):** `claude/session-close` still carries an unmerged
  bookkeeping commit `445e9dd` (last session's HANDOFF/README writeup) that never landed on `main`.
  I based this branch on `main` to keep the #10 diff clean, so it's untouched — Nadim's call whether
  to merge it.

## 2026-07-03 - Codex: review of frequent-areas sample-size cue on `codex/frequent-areas-sample-cue-review` - CLEAR

Reviewed `origin/claude/frequent-areas-sample-cue` at `3cae3a0` against `main` (`d5a2d79`).
Verdict: **CLEAR**. I made no code fixes. Nadim still merges; this branch records only the Codex
review verdict above Claude's tip.

### Review notes
- `sampleSize()` is correct: it prefers the serialized
  `frequent_areas_confidence.total_window_records` (`app/analysis/bridge.py:41`,
  `app/analysis/bridge.py:64`; frozen source returns it at `phase1_cdr/detection.py:331`). The
  fallback is also sound because `detect_frequent_areas()` emits `share = count / total`
  (`phase1_cdr/detection.py:278`), so `Math.round(top.count / top.share)` reconstructs the same
  total for legacy result JSON.
- Empty/older payload handling is safe: `sampleSize()` returns `null` when `conf` is absent, `areas`
  is empty, or the top share is not positive (`app/web/js/components.js:180`), and both render sites
  only call the note inside the non-empty frequent-areas branch (`app/web/js/screens/results.js:96`,
  `app/web/js/screens/spreadsheet.js:362`).
- No XSS regression: the note is produced through the shared `el()` helper, whose string path uses
  `document.createTextNode()` and has no `innerHTML` sink (`app/web/js/components.js:10`,
  `app/web/js/components.js:18`).
- I agree with the design call: state N plainly, do not restore a confidence pill, and do not copy
  frozen home/work N thresholds into JS. A frequency ranking is descriptive; the honest transferable
  cue is the observed record count, not a new gated verdict.
- The orphaned-field cleanup is accurate: `frequent_areas_confidence` now feeds the sample-size note
  in Results and Spreadsheet (`app/web/js/screens/results.js:62`,
  `app/web/js/screens/spreadsheet.js:362`). The `API-MISMATCH #8` comment now matches the behavior
  (`app/web/js/screens/results.js:4`).
- `phase1_cdr/` remains byte-frozen versus `main`. WSL pytest caused the known line-ending churn in
  two fixtures; I restored only `phase1_cdr/` as instructed, and `git diff --stat main -- phase1_cdr/`
  is empty.

### Verification
- WSL `/root/lp-venv`: `pytest tests/phase2a tests/architecture phase1_cdr/tests` -> **187 passed**.
- WSL `/root/lp-venv`: `ruff check app tests main.py` -> clean.
- Native Node: `node --check` clean for `app/web/js/components.js`,
  `app/web/js/screens/results.js`, and `app/web/js/screens/spreadsheet.js`.
- Native PowerShell `ruff` is not on PATH here; the documented WSL gate above ran successfully.

## 2026-07-03 - Claude: frequent-areas sample-size cue on `claude/frequent-areas-sample-cue` - FOR REVIEW

Nadim pushed back on Khaled's removal of confidence from frequent areas/contacts. Conclusion after
grounding it in the frozen algorithm: dropping the confidence **pill** was right (a frequency
ranking is a description, not a gated inference — three of the four home/work gates, closeness/
density/near-tie, have no referent for a tally; contacts have none by explicit design:
`detect_frequent_contacts` docstring says "not an inference, so no confidence gates apply"). BUT one
gate transfers to any tally: **N (sample size)**. And the frozen `detect_frequent_confidence` is
**share-gate only** (a pure ratio), so it rates "100% of 3 records" as High — actively misleading on
thin data. So the honest sufficiency signal is N itself, shown descriptively, never as a pill.

### Change (frontend only; backend/API/Phase-1 all untouched)
- `app/web/js/components.js`: new `sampleSize(areas, conf)` + `sampleNote(areas, conf)`. N comes from
  `frequent_areas_confidence.total_window_records` (this is the **one consumer** of that
  previously-orphaned computed-and-stored field — resolves that loose end), with a fallback deriving
  N from the top area's `count/share` for older stored results. No invented "thin data" threshold —
  the note states N plainly ("Ranking of N records — read the shares to judge how firm it is").
- `app/web/js/screens/results.js` + `screens/spreadsheet.js`: frequent-areas card now renders the
  note under the "count, not a verdict" kicker. The `API-MISMATCH #8` comment updated: the field is
  no longer "deliberately NOT rendered" — it feeds the sample-size note (not a pill).

### Deliberately NOT done
- No pill restored (that was the right removal). No new N threshold/gate invented in the UI.
- Export (`analysis/export.py`) not touched — it could gain a record-count column later; out of scope.

### Verification (WSL): **187 passed** (no backend change), `node --check` on the 3 touched JS files
clean, `git diff --stat main -- phase1_cdr/` empty (restored the /mnt/c eol churn per the standing note).

### For Codex/Nadim
- Pure display addition; review the framing (is "N records, read the shares" the right honest cue?).
- Not merged. Sits on `main`; independent of issues #14-#17.

## 2026-07-03 - Codex: review of spreadsheet stack on `codex/spreadsheet-review` - CLEAR

Reviewed from fetched Git state, not snapshot assumptions:
- Feature layer: `git diff main...origin/spreadsheet`.
- Fix layer: `git diff origin/spreadsheet...origin/claude/spreadsheet-fixes`.
- History: `git log --oneline main..origin/claude/spreadsheet-fixes`.

### Verdict
**CLEAR.** I did not make code fixes. Nadim still merges; this branch only records the Codex
review verdict above Claude's fix-layer tip.

### Review notes
- SQL safety checks pass: `analysis/repo.py:frequency` and `datasets/repo.py` keep all values
  parameterized; `rank_by`/`sort` are limited by `FREQUENCY_FIELDS` / `RECORD_SORT_FIELDS`;
  `_like_pattern()` escapes backslash, `%`, and `_` with `ESCAPE '\'`; the midnight-wrapping hour
  window composes correctly; timestamp `substr()` usage matches the validated naive ISO-8601
  storage format.
- Export checks pass: `analysis/export.py` reads the keys serialized by `bridge.py`;
  `analysis/routes.py:export_results` owns the unit-of-work (`repo` read -> `EXPORT` audit ->
  commit); the endpoint is POST-only; the only live JS caller uses bodyless `fetch(...,
  {method:"POST"})`, so `login_required`'s JSON content-type guard does not fire; the existing
  fetch->blob download path still applies. GET is pinned to 405 by test.
- Call-type labels in `call-types.js` match frozen Phase 1 constants:
  `1=out call`, `2=in call`, `11=out SMS`, `22=in SMS`.
- I agree with Claude's fix-layer decisions: the detection `seq` guard is shared across `refresh()`
  slot/button rebuilds and closes the stale-render race between runs; frequency area filtering
  should stay case-insensitive exact (`COLLATE NOCASE`), not substring, so `Hamra` and `Hamburg`
  are not merged; ASCII-only NOCASE is acceptable for the synthetic fixture vocabulary; explorer
  state restore is adequate for the refresh path; `loadUsers()` now has latest-wins parity and
  clears/rebuilds only after the awaited list returns; the `renderTally()` empty-vs-null-ranked split
  and repeated `.xlsx` filename collapse are correct.
- I agree the deferred items #14-#17 are non-blocking for this stack.

### Verification
- WSL `/root/lp-venv`: `pytest tests/phase2a tests/architecture phase1_cdr/tests` -> **187 passed**.
- WSL `/root/lp-venv`: `ruff check app tests main.py` -> clean.
- WSL `/root/lp-venv`: `lint-imports` -> 4 contracts KEPT.
- Bundled Node `--check`: `spreadsheet.js`, `api.js`, `export.js`, `call-types.js`, `results.js` -> clean.
- `git -c core.autocrlf=false diff --stat main -- phase1_cdr/` -> empty.
- Native Windows pytest remains blocked by Application Control on pandas DLLs; the canonical WSL gate
  above ran successfully.

## 2026-07-03 - Claude: code-review fixes round 2 (#5,#6,#8,#10) on `claude/spreadsheet-fixes` - FOR REVIEW

Follow-up on the same branch after #1-#4 (entry below). Nadim asked to also take the cheap,
worthwhile findings; I applied the Tier-1 set plus the 1-line #5 consistency touch-up, and
**deliberately left #7 (call_type validation consistency — Khaled's call) and #9 (duration-toggle
refetch — works, the real fix is a client-side re-render refactor disproportionate to a cosmetic
win)**.

- **#6 Explorer state-wipe** (`spreadsheet.js` `explorerCard.refresh`): refresh() rebuilt every
  field from scratch, so creating a target by clicking a phone in the grid wiped the explorer's
  in-progress selection + typed filters (the click targeted the Detection card, not the explorer).
  Now snapshots the 8 field values by id before `clear(inner)` and restores them after rebuild
  (setting a `<select>` to a since-deleted target is a no-op → falls back to the prompt). Mirrors
  `detectionCard.refresh`'s existing `keep`. (JS-only.)
- **#8 `loadUsers()` race** (`spreadsheet.js`): the phone-filter rebuild had no in-flight guard, so
  fast dataset switches could leave it listing the wrong dataset's numbers. Added a `userSeq`/`mine`
  guard (same pattern as the records `load()`), and moved the clear+rebuild to *after* the await so a
  superseded response can't mix options. (JS-only.)
- **#5 Export Summary KeyError parity** (`app/analysis/export.py`): the Summary "Frequent areas"
  cell used `a['area']`/`a['count']` while the detail loop two lines below used `.get()`; a
  partial/legacy `frequent_areas` entry would KeyError the *whole* workbook. Switched to `.get()` so
  it degrades to a blank cell instead (cheap consistency fix — I did NOT add full per-row
  try/except; a malformed top-level `json.loads` still fails, which is tampered-DB territory).
  Test: `test_build_workbook_tolerates_partial_frequent_area`.
- **#10 Filename double-`.xlsx`** (`app/web/js/screens/export.js`): the sanitizer stripped only one
  trailing `.xlsx`, so `report.xlsx.xlsx` → `report.xlsx.xlsx`. Now `replace(/(\.xlsx)+$/i, "")`
  collapses a repeated extension. (JS-only.)

### Verification (WSL): **187 passed** (186 → +1), ruff clean, lint-imports 4 KEPT, node --check on
the 3 touched JS files clean, `git diff --stat main -- phase1_cdr/` empty.

### Still open — now filed as GitHub issues (non-blocking, for later):
- **#14** call_type validation inconsistency across endpoints (review finding #7).
- **#15** duration unit toggle triggers a full server refetch (review finding #9).
- **#16** frontend duplication between `results.js` and `spreadsheet.js` (pct/detection renderer/
  field helper; `downloadResultsXlsx` vs `request()`) — pure cleanup.
- **#17** minor UX hardening: `callTypeDisplay(null)` → "null", export filename control/bidi chars.

## 2026-07-03 - Claude: code-review fixes #1-#4 on `claude/spreadsheet-fixes` - FOR REVIEW

Branched off `origin/spreadsheet` (Khaled's feature branch, in review). A high-effort code review
of that branch surfaced 10 findings; this fixes the top 4 (the correctness-relevant ones). The
other 6 (export not resilient to a malformed/partial stored `result_json`, call_type validation
inconsistency between the records vs frequency endpoints, `loadUsers()` in-flight race, duration
unit-toggle full refetch, filename double-`.xlsx`, plus a duplication cluster between `results.js`
and `spreadsheet.js`) are left for a follow-up / Khaled's call.

### Fixed (each with a regression test where testable)
1. **Detection stale-render race** (`app/web/js/screens/spreadsheet.js` `detectionCard.run`):
   `run()` had no latest-wins guard, so two fast phone-clicks in the Records grid (`runFor` bypasses
   the button's `disabled`) could render subscriber A's home/work under B's selection — the
   worst-case failure for this app. Added a `seq`/`mine` token mirroring the records `load()` guard;
   a superseded run neither renders nor re-enables the button. (JS-only; covered by `node --check`.)
2. **Frequency "No records match" lie** (`spreadsheet.js` `renderTally`): the empty-state fired on
   `total_records === 0 || top.length === 0`, so an all-NULL ranked column (e.g. rank-by-partner over
   location-only rows) reported "no records match" when N matched. Split into two messages: true-empty
   vs "N record(s) match, but none carry a value for this ranking." (JS-only.)
3. **Frequency `area` filter case-sensitivity** (`app/analysis/repo.py` `frequency`): was `area = ?`
   (case- and whitespace-exact) while the Records grid's area filter is ASCII case-insensitive LIKE,
   so `hamra` typed in the explorer returned 0 for `Hamra`. Now `area = ? COLLATE NOCASE`. Kept
   **exact** (not substring) on purpose — the field's placeholder is "exact area" and a tally must
   not merge `Hamra` with `Hamburg`. Test: `test_frequency_area_filter_is_case_insensitive`.
4. **Export was a committing GET** (`app/analysis/routes.py` `export_results`): it writes an EXPORT
   audit row + commits, but a GET is auto-given a HEAD by Flask and is prefetch/reload-idempotent —
   each of which logs a phantom export where no bytes leave. Changed to **POST** (bodyless, so
   `login_required`'s JSON-content-type guard doesn't apply, same as `analyze`). Updated the caller
   (`app/web/js/api.js` `downloadResultsXlsx` → `fetch(url, {method:"POST"})`; the download is already
   fetch→blob so nothing else changes), the 7 test calls in `test_export.py`, and `docs/reference/api.md`.
   New test `test_export_rejects_get` asserts 405.

### Verification (WSL `/root/lp-venv`, the canonical Linux/3.11 path)
- `pytest tests/phase2a tests/architecture phase1_cdr/tests` → **186 passed** (184 → +2 regression).
- `ruff check app tests main.py` → clean. `lint-imports` → 4 contracts KEPT.
- `node --check` on the two changed JS files → clean. `git diff --stat main -- phase1_cdr/` → empty.

### Left for Codex/Nadim
- This branch sits on top of `origin/spreadsheet`; review it as the incremental diff
  (`git diff origin/spreadsheet...claude/spreadsheet-fixes`). Merge order is Nadim's call — either
  fold into `spreadsheet` before it merges, or land right after.
- The 6 non-fixed findings above are documented for a deliberate follow-up; none are blockers.

## 2026-07-03 - Claude: Home/Work result cards were not level - FOR REVIEW

One-line CSS fix (`9fe7a61`): `.card + .card { margin-top: var(--s4) }` — the stacked-cards
spacing rule — also matched the side-by-side Home/Work cards inside `.result-grid` on the
Results screen, dropping the Work card 16px below Home. Added
`.result-grid > .card + .card { margin-top: 0 }` (the grid gap owns all spacing there,
including the ≤880px one-column collapse, where the gap still applies).

How it was found/verified (worth keeping as a pattern): static repro page with the real
app.css measured via Playwright `getBoundingClientRect`, then a live check against a
headless seeded server (`create_app()+ui_bp`, temp APP_DATA_DIR, sample_data.csv imported,
target analyzed) — Results screen and Spreadsheet detection panel both measure level now.
Note: the Spreadsheet panel's `.det-block`s never had the bug (no `.card` selector match);
Khaled reported both tabs, but only the Results screen was actually offset.

## 2026-07-02 - Claude: Export file-name picker on `spreadsheet` - FOR REVIEW

Small SPA-only follow-up: the Export screen gets a "File name" text input (default
`lapassion_results`). Client-side only — the name feeds the download anchor's `download`
attribute in `api.js:downloadResultsXlsx(targetId, filename)`; filesystem-illegal characters
stripped, `.xlsx` appended exactly once, blank falls back to the default. No backend change
(the server's Content-Disposition stays the generic default; the anchor name wins in-app).
Khaled also asked for frequent contacts in the export — already there since round 4
(third sheet); pointed him at the sheet tabs.

## 2026-07-02 - Claude: Spreadsheet round 4 — column sorting + export workbook redo on `spreadsheet` - FOR REVIEW

Two changes from Khaled's third pass:

1. **Sortable Timestamp/Duration columns** — clicking the header toggles oldest/newest
   (Timestamp) or shortest/longest (Duration). Server-side so it spans all pages and composes
   with the header filters: `sort` (whitelisted `RECORD_SORT_FIELDS` in `datasets/repo.py`,
   ValueError on anything else as defense-in-depth; route treats unknown as unsorted) +
   `dir=asc|desc` on GET /records; `ORDER BY <col>, id` tie-break keeps paging stable.
2. **Export workbook reorganized** (`analysis/export.py` rewrite) — three sheets:
   `Summary` (one row per target: home/work areas + their confidence, compact frequent-areas
   text), `Frequent areas` (ranked rows: rank/area/count/share as a real % cell), and
   `Frequent contacts` (per-contact call/SMS splits, previously not exported at all).
   **Frequent-areas confidence removed entirely** (header + cells) — same "a count is not a
   verdict" rule as the UI; the stored payload still carries it, export just doesn't render it.
   Styling: bold white-on-slate header row, frozen top row, autofilter on every sheet,
   content-sized column widths, italic-gray "not analyzed".

Verified: 184 passed (178 → +4 sort, +2 export), ruff clean, lint-imports 4 contracts KEPT,
phase1_cdr diff vs main empty. api.md updated (records sort params + workbook layout note).


Four changes from Khaled's second live pass:

1. **In-sheet column filters** — the Records table now has a filter row inside the sheet's header
   (autofilter-style): Phone (select), Area (substring), Type (select), Other party (substring),
   all composable and applied **server-side** so paging/totals stay right. Backend:
   `phone_number`/`call_type` exact + `area`/`other_party` case-insensitive substring on
   `GET /datasets/<id>/records` (`datasets/repo.py:_records_where`; LIKE wildcards escaped,
   pinned by test). Malformed `call_type` ignored, consistent with the route's paging fallback.
   Table skeleton is static (only tbody/pager re-render) so typing keeps focus; stale responses
   dropped via a sequence guard.
2. **Click a user → detection** — phone cells are buttons; clicking ensures a target exists for
   that dataset+phone (auto-created via existing POST /targets, named after the number, CONFLICT
   treated as success) then scrolls to the Detection card and runs the full-set analysis there.
   Detection/explorer cards got a `refresh(targets)` rebuild so new targets appear in pickers.
   No new analyze surface: same target-based endpoint, same audit/persist path.
3. **Duration unit toggle** — Records top bar: seconds (default) / minutes (1 decimal).
   Display-only; the stored value stays `duration_seconds`.
4. **Frequent areas/contacts lose the confidence pill** — they're counts, not gated verdicts
   (Khaled's call). Removed pill + overall-area gate trace on the Results screen and the pill in
   the Spreadsheet detection panel; replaced with a "count, not a verdict" kicker.
   `frequent_areas_confidence` stays in the API payload (frozen Phase 1 computes it; stored
   results keep it) — this is render-only. API-MISMATCH #8 comment updated to say so.

Verified: 178 passed (172 → +6 filter tests), ruff clean, lint-imports 4 contracts KEPT,
phase1_cdr diff vs main empty. api.md records row updated.


Three fixes/changes after Khaled used the new tab in the desktop window:

1. **Export downloaded nothing in the desktop app** — pywebview cancels every download unless
   `webview.settings["ALLOW_DOWNLOADS"]` is True (default False), so the Export button silently
   no-oped in the PyWebView window while working in a plain browser (which is where the previous
   entry's end-to-end pass ran — lesson noted). Fixed in `main.py:main()`; WebView2 now shows its
   native download UI. No backend change.
2. **Records user filter** — filter bar at the top of the Records card: Dataset + User selects
   (`app/web/js/screens/spreadsheet.js:recordsCard`). User options come from the existing
   `/phone-numbers` endpoint with per-user record counts. Backend: optional exact-match
   `phone_number` query param on `GET /api/datasets/<id>/records` (`datasets/routes.py`,
   `datasets/repo.py:count_records/read_records_page`); `total` counts the filtered set so paging
   stays correct; empty param = all users. +4 tests (`test_spreadsheet.py`, 168 → 172); api.md row
   updated.
3. **Call types show code AND wording** — new `callTypeDisplay()` in `call-types.js` renders
   "out call (1)" etc.; used in the records Type column (tooltip dropped), the explorer's call-type
   filter options, and rank-by-call_type tally values. Codes remain the stored/submitted values.

Verified: 172 passed, ruff clean, lint-imports 4 contracts KEPT (native AMD64), phase1_cdr diff
vs main empty. Frequency explorer unchanged by request.


Khaled's brief (originally written for a Streamlit app; adapted to our Flask/SPA architecture —
no Streamlit exists in this repo). Three additive features, existing screens untouched:

### 1. Spreadsheet tab (`#/spreadsheet`, rail nav item)
- **Records**: read-only paged table of `cdr_records` (all 9 columns + id). New
  `GET /api/datasets/<id>/records?offset&limit` (`datasets/repo.py:count_records/read_records_page`).
- **Detection panel**: target picker → existing `POST /analyze` (persists + audits, same as the
  Targets screen) → home/work/frequent-areas rendered with the shared `confidencePill`/`gateTrace`.
  Always the FULL record set; the card says why (gates depend on N).
- **Frequency explorer**: `GET /api/targets/<id>/frequency` — filters compose (call_type, exact
  area, date range, hour-of-day range **with midnight wrap**, e.g. 22→6) and `rank_by` ∈
  {area, other_party, call_type} (whitelist — identifiers can't be bound). Response is deliberately
  a bare tally `{target, rank_by, total_records, top:[{value,count}]}` — NO confidence/gates, and
  `test_frequency_is_a_tally_not_a_detection` pins that contract. NULL rank values excluded from
  ranking but counted in total. UI: warn-colored card + "descriptive count · filtered slice" kicker
  vs the accent "inference · full record set" kicker, so a tally is never read as a verdict.

### 2. App-wide export (`#/export`, rail-foot item, visible on every screen)
- `GET /api/export/results.xlsx?target_id=<id|all>` → openpyxl workbook of the **stored** latest
  answers per target (never recomputes; `analysis/repo.py:targets_with_latest_result` picks
  latest-by-id per target, LEFT JOIN so un-analyzed targets export as "not analyzed").
  Builder in new `app/analysis/export.py` (DOMAIN; added to the import-linter layer line).
- **Decision to review**: export writes an `EXPORT` audit row (the one audited GET) — data leaving
  the encrypted store is what the trail is for. Veto if you disagree with a committing GET.

### 3. Call-type labels (display-only)
- Single lookup `app/web/js/call-types.js` mirroring frozen `detection.py:105-108`:
  **1=out call, 2=in call, 11=out SMS, 22=in SMS**. NOTE: the brief guessed the pairing the other
  way around (1="in SMS"…) but said to trust the source — the source won. Numeric codes stay the
  stored/filter/API values everywhere; labels are render-time only (records table, explorer filter,
  rank-by-call_type results; raw code kept in the cell tooltip).

### Verification (native Windows — this AMD64 machine imports pandas fine; the Smart-App-Control
workaround only applies to the ARM64 machine)
- `pytest tests/phase2a tests/architecture phase1_cdr/tests` → **168 passed** (was 143; +25).
- `ruff check app tests main.py` → clean. `lint-imports` → 4 contracts kept (114 deps).
- `node --check` on all touched JS → clean. `git diff --stat main -- phase1_cdr/` → empty.
- NOT yet exercised: the real PyWebView app end-to-end (only Flask test-client + JS parse).

### Left for Codex/Nadim
- Review the EXPORT-audits-on-GET decision and the frequency param policy (records paging falls
  back to defaults like analyze's top_n; frequency filters 400 on malformed values — asymmetric
  on purpose: filters silently ignored would lie about what was counted).
- Smoke the UI in the desktop shell (`python main.py`): Spreadsheet tab, explorer, export download.

## 2026-07-02 - Claude: session close — deep-audit thread MERGED to main, branches pruned

- CI green on `codex/deep-audit-fixes-review` → Nadim had me fast-forward **main to `d211156`**
  (Claude's `d2a8ced` audit fixes + Codex's logout fail-closed fix) and push. Both audit branches
  deleted local + origin; only `main` remains.
- Final verified state on main: **143 passed** (WSL full suite), ruff clean, 4 import-linter
  contracts kept, `git diff --stat main -- phase1_cdr/` empty.
- CLAUDE.md test count refreshed 136→143.
- The two audit entries below carry the full record: what was fixed, what was audited clean, and
  the document-only findings (phase1.py path shadowing, api.js message-text 401 discrimination,
  etc.) — revisit those before production if desired.
- Phase 3 remains parked; first move unchanged (wire `migrations.migrate(g.db)` into
  `app/api/guards.py:get_db()`, then auth de-globalization per `docs/phase3-surface.md`).

## 2026-07-02 - Codex: review of `claude/deep-audit-fixes` on `codex/deep-audit-fixes-review` - CLEAR WITH LOGOUT FIX

Reviewed Claude's pushed branch from git, not snapshot state:
`git fetch --all`, `git log --oneline main..origin/claude/deep-audit-fixes`
(`d2a8ced claude: deep audit fixes`), and
`git diff main...origin/claude/deep-audit-fixes`, then read the top handoff entry.

### Verdict
- Agree with the setup/login fail-closed semantics. An unauditable setup/login should not leave
  `DB_KEY`/`USERNAME`/the client session live behind a 500.
- Agree with deliberately not applying the same revocation to change-password: by the time its audit
  write runs, the password sidecar rewrite has already happened, so session revocation would not
  restore the unit of work or make the missing audit row less true.
- Agree the documented "not fixed" items can stay document-only for this pre-production pass:
  `infra/phase1.py` path shadowing, frontend exact-message 401 discrimination, multi-tab cosmetic
  refresh rejection paths, `latest_result` corruption surfacing as 500, local self-DoS upload shapes,
  pytest in runtime requirements, and overlapping setup requests.

### Fix made by Codex
- `app/auth/routes.py`: logout now clears local auth state in a `finally` around the `LOGOUT` audit
  write. Claude's refactor reused `_lock()`, but the old ordering still left the process/session
  authenticated if the logout audit write raised. A failed logout should fail closed too: return the
  500, but revoke local access.
- `tests/phase2a/test_transaction_semantics.py`: added
  `test_audit_failure_during_logout_fails_closed`.

### Checks
- `.venv\Scripts\python.exe -m pytest tests\architecture` -> 4 passed.
- `.venv\Scripts\ruff.exe check app tests main.py` -> clean.
- `git diff --stat main -- phase1_cdr/` -> empty.
- Full `tests/phase2a tests/architecture phase1_cdr/tests` not run natively here because this Windows
  machine still cannot import pandas under Smart App Control; rely on Claude's WSL run and CI for the
  pandas-backed suite. The new phase2a logout regression is intentionally covered for CI/WSL.

## 2026-07-02 - Claude: deep audit + focused fixes on `claude/deep-audit-fixes` - FOR REVIEW

Full-repo debug/correctness/architecture/security audit (pre-production pass, per Nadim), then
focused fixes only. Reviewed every module in `app/`, `main.py`, the SPA (`app/web/`), all of
`tests/`, CI, and dependency configs; Phase 1 read-only for contract checks.

### Fixed (each with a regression test)
- **Fail-closed login/setup on audit failure** (`app/auth/routes.py`): if the SETUP/LOGIN_SUCCESS
  audit write failed, the 500 left `DB_KEY`/`USERNAME`/session set — a half-committed unit of work
  (the session grant IS that route's unit of work). Now `_lock()` clears all three before
  re-raising; `logout` reuses `_lock()`. Tests: `test_transaction_semantics.py` (`*_fails_closed`).
  Deliberately NOT applied to change-password: its audited action (the file rewrite) is already
  irrevocable, so revoking the session there would undo nothing.
- **Failed-login sidecar is now best-effort in code, not just in its docstring**
  (`app/audit/log.py:write_failed_login`): an OSError writing `login_failures.log` used to escape
  the login route's `except AuthError` block and turn the 401 into a 500. Now caught + WARNING-logged.
  Test: `test_auth.py::test_failed_login_still_401_when_sidecar_unwritable`.
- **Validation parity with the frozen loader** (`app/datasets/validation.py:_parse_integer`):
  `int("1_1") == 11` under PEP 515, but Phase 1's `pd.to_numeric` rejects underscores — the app
  imported rows the frozen loader would drop. Underscore-bearing numeric strings are now skipped.
  Tests: `test_validation.py::test_underscore_*`.
- **Boundary gap: `app.ui` was invisible to import-linter** (`pyproject.toml`): not in the layers
  contract and not in the Phase-1 forbidden source list, so `app/ui.py` could have imported
  `detection`/`loader` (or higher layers) with CI green. Added to both (now 109 deps analyzed, 4 kept).
- **AST scanner gap** (`tests/architecture/test_boundaries.py`): the no-SQL-in-routes scan only
  globbed `app/*/routes.py`; now also covers the other route-bearing modules `app/api/system.py`
  and `app/ui.py`.
- **Missing coverage**: the 415 `BAD_CONTENT_TYPE` guard (light CSRF hardening in `login_required`)
  had zero tests. Added `test_auth.py::test_state_changing_non_json_body_is_415`.

### Audited clean (no change needed)
SQL injection (all binds parameterized; `PRAGMA key` interpolates hex only), path traversal
(`send_from_directory` everywhere), XSS (SPA renders exclusively via the textContent DOM builder —
no innerHTML sinks), secrets in logs/responses (none), crypto usage (fresh GCM nonce per wrap, salt
per KDF, key-length check on unwrap), migration atomicity + v0 adoption fingerprint, teardown
implicit-rollback semantics (pinned by existing tests), CSRF/DNS-rebinding under
SameSite=Strict + per-launch SECRET_KEY + ephemeral port, detection NaN paths (all divisions
guarded), and the repo/route/domain layering.

### Found but deliberately NOT fixed (documented so review can disagree)
- `infra/phase1.py` `sys.path.insert(0, ...)` shadows top-level names (`main`, `dev_fixtures`) for
  the whole process; `test_main.py` already works around it. Reordering the frozen seam's path is
  riskier than the wart.
- `api.js isLocal401()` distinguishes change-password 401s by exact message text ("login required");
  correct today but brittle — a distinct error code would be an API change, defer to a deliberate rev.
- Screens re-invoke themselves after delete/add without catching rejections (`targetsScreen`,
  `datasetsScreen`) — a dataset deleted in another tab can leave a stuck screen; needs multi-tab
  misuse, cosmetic exposure only.
- `latest_result` 500s (clean JSON envelope, Flask logs it) on hand-tampered `result_json`; treating
  corruption as 404 would hide it, so current behavior kept.
- xlsx zip-bomb / million-bad-row upload = self-DoS on a local single-user app; compressed size is
  capped (50 MiB).
- `requirements.txt` carries `pytest` (test tooling) as a "runtime" dep and CI's phase2a job relies
  on that; relocation would touch CI for pure hygiene.
- Two overlapping `/api/setup` requests can interleave `create_account` (last `_save` wins; the
  wrong-key stale-db path self-heals on retry). Unreachable from the SPA (button disabled on submit).

### Verification
- WSL (`/root/lp-venv`): `pytest tests/phase2a tests/architecture phase1_cdr/tests` → **142 passed**
  (was 136; +6 regression tests). `ruff check app tests main.py` → clean. `lint-imports` → 4 contracts
  kept (incl. the widened ones).
- `git diff --stat main -- phase1_cdr/` → empty (WSL eol churn on the two fixture files was restored
  with `git checkout`, per the standing note below).

### Left for Codex/Nadim
- Review the fail-closed login semantics (behavior change: an unauditable login now grants no
  session — previously it 500'd but left you logged in). This is the only user-visible change.
- Phase 3 remains parked; nothing here touches the global-auth surface map.

## 2026-07-01 - Claude: session close — prep MERGED, Dependabot triaged, local WSL testing established

Session wrap-up. Everything below in the pre-Phase-3 prep thread is now **landed on `main`**; Phase 3
remains parked until Nadim starts it.

### What's on `main` now (tip after this entry's commit)
- **Pre-Phase-3 prep MERGED** (`5f736ec`, was `claude/pre-phase3-prep` + Codex's review commit): the docs
  bundle (`docs/reference/api.md`, `docs/reference/schema.md`, `docs/phase3-surface.md`) + operational
  logging (`app/infra/logging_config.py`, wired in `create_app`, silent-swallow spots now logged) +
  Codex's 3 fixes (login 400 in api.md, corrected line refs in phase3-surface.md, `app.infra.logging_config`
  added to the Phase-1 forbidden import-linter list). CI was green on all jobs before merge. Both branches pruned.
- **Dependabot triaged** (from PR #11's config, now active): **#12** (`actions/setup-node` v4→v6) MERGED
  (`ff5c8a7`) — clears the Node-20 deprecation warning. **#13** (numpy 2.4.6→2.5.0) CLOSED — no py3.11
  wheel exists, so `-c constraints.txt` install fails (`ResolutionImpossible`); the lock correctly blocked
  a bad bump. Dependabot re-proposes only when a 3.11-compatible numpy exists (or if the backend's Python
  floor is deliberately raised to 3.12 — a separate decision).
- **Earlier this session** (already recorded below / prior sessions): stale `claude/session-close` branch
  pruned; PR #11 (GitHub security foundation) rebased onto current main and MERGED; `.gitignore` now covers
  `.claude/`, `session-logs/`, `sample_cdr_data.xlsx`; CLAUDE.md reorg banner de-staled + `AGENTS.md` added.

### Local testing restored (NEW capability — see `local-testing-wsl` auto-memory)
Native Windows on this ARM64 box **cannot import pandas** — Smart App Control (enforced, one-way) blocks
unsigned compiled `.pyd`s, so `pytest tests/phase2a` fails there. We did NOT disable SAC (irreversible).
Instead set up **WSL2 Ubuntu 26.04** with a uv-managed **Python 3.11** venv at `/root/lp-venv`
(requirements + requirements-dev under constraints). Full local run there: **136 passed**, ruff clean,
4 import-linter contracts kept — full CI parity, first time locally. Command is in the auto-memory.
`lint-imports` now runs locally in WSL too (grimp has aarch64 wheels; win_arm64 still can't).

### Housekeeping / caveats
- Phase 1 stays **frozen**: a WSL run via `/mnt/c` flipped line endings on `ground_truth.json` /
  `sample_data.csv` (content-identical); restored with `git checkout` — tree clean. Note WSL edits under
  `/mnt/c` can re-trigger this eol churn; restore rather than commit it.
- CLAUDE.md refreshed: test count 125→136, local-testing/WSL note, `docs/reference/` + `AGENTS.md` in Key docs.

### Next session (Phase 3, when Nadim says go)
First move unchanged: wire `migrations.migrate(g.db)` into `app/api/guards.py:get_db()` (ADR 0002), then
auth de-globalization — the exact call-site inventory is now in `docs/phase3-surface.md`.

## 2026-07-01 - Codex: review of `claude/pre-phase3-prep` on `codex/pre-phase3-prep-review` - CLEAR WITH SMALL FIXES

Reviewed Claude's pushed branch (`0d71b02 claude: pre-Phase-3 prep - reference docs + operational logging`)
against `main`, trusting git (`git fetch --all`, `git log main..origin/claude/pre-phase3-prep`,
`git diff main...origin/claude/pre-phase3-prep`) and then reading the top handoff entry.

### Verdict
- No behavioral blocker found. The logging changes are genuinely additive:
  `account.py` still re-raises after both cleanup failures, the import parse failure still returns the
  same `400 BAD_FILE`, and no response/status/data-write/control-flow change showed up in the diff.
- `app/infra/logging_config.py` is pure INFRA (stdlib only), and route/domain modules only use
  `logging.getLogger(__name__)`.
- Logging hygiene looks right: no passwords, DB keys, wrapped keys, salts, or secrets are logged.
  The direct probe leaves one tagged handler after repeated `configure_logging()` calls, level INFO,
  and `propagate=False`.
- Docs are now accurate for the spot-checked route/schema/auth-surface items.

### Fixes made by Codex
- `docs/reference/api.md`: added the real `400 BAD_REQUEST` missing/blank-credential path for
  `POST /api/login`.
- `docs/phase3-surface.md`: corrected the `datasets/routes.py` `current_username()` line refs to
  the post-logging lines (`L66`, `L98`).
- `pyproject.toml`: added `app.infra.logging_config` to the Phase-1 forbidden import-linter source
  list so the new non-seam infra module is covered by the same "Phase 1 only via infra.phase1" gate.

### Checks
- `pytest tests\architecture` -> 4 passed.
- `.venv\Scripts\ruff.exe check app tests main.py` -> clean.
- Direct `configure_logging()` idempotency probe -> one tagged handler, INFO, `propagate=False`.
- `pyproject.toml` parsed with stdlib `tomllib`.
- `rg "DB_KEY|USERNAME|current_username|get_db|session\[|authenticated"` matched the Phase 3 surface
  map; no unlisted live global-auth call site found in `app/`.
- `git diff --stat main -- phase1_cdr/` -> empty (Phase 1 untouched).
- Full suite (`tests\phase2a tests\architecture phase1_cdr\tests`) could not run locally: importing
  pandas still fails on this machine with `ImportError: DLL load failed while importing tslib: An
  Application Control policy has blocked this file`.
- `lint-imports` could not run locally: `.venv` has no `lint_imports` module installed. The edited
  contract is syntactically valid, and CI remains the real import-linter gate on Ubuntu.

### Left for Nadim/CI
- No known blocker. CI should still run the full test, phase2a, boundaries, and frontend jobs before
  Nadim merges. Phase 3 remains parked.

## 2026-07-01 - Claude: pre-Phase-3 prep (docs bundle + operational logging) on `claude/pre-phase3-prep` - FOR REVIEW

Nadim asked to prep everything before Phase 3 (Phase 3 itself stays parked). After a full read-only
architecture audit against a 22-point enterprise checklist, we agreed only two items are worth doing
now; the rest are either cargo-cult for a local single-user app or better done *inside* Phase 3.

### What changed (behavior-additive; no API/response/data changes)
- **Docs bundle (zero code risk):**
  - `docs/reference/api.md` — full endpoint reference (built by reading `app/*/routes.py`).
  - `docs/reference/schema.md` — DB schema mirror of `migrations.py:_BASELINE` + sidecars + migration rules.
  - `docs/phase3-surface.md` — exact inventory of the 3 global-auth slots + every call site Phase 3 must
    touch (the de-globalization map, so Phase 3 is a mechanical swap not a re-discovery).
- **Operational logging (small, additive):**
  - New `app/infra/logging_config.py` — `configure_logging()`, idempotent, level from `LA_PASSION_LOG_LEVEL`
    (default INFO), tags its handler so repeated `create_app()` in tests doesn't pile up handlers.
    Pure INFRA (stdlib only). Distinct from the *audit* trail.
  - `app/__init__.py` calls it first thing in `create_app()`.
  - Logged the previously-silent swallow spots: two `except OSError: pass` in `account.py` (temp-file /
    stale-db cleanup) → `logger.warning`; the `read_excel` parse failure in `datasets/routes.py` →
    `logger.info(exc_info=True)` (user still gets the clean 400; the real error is kept server-side).

### Deliberately NOT done (documented in the audit, agreed with Nadim)
Interfaces/ABCs, DI container, rate limiting, config files, `develop` branch → cargo-cult here.
Typed row models (TypedDict) → deferred to Phase 3, which churns the very row shapes (multi-account
owner columns). `ruff format`/.editorconfig → skipped as low-value.

### Verification (partial locally — see caveat)
- `pytest tests/architecture` → **4 passed** (boundaries intact; new infra module + route logging don't
  break layering).
- `configure_logging()` idempotency probe → 1 tagged handler after two calls, INFO level.
- `ruff check` on all changed files → clean.
- `git diff --stat -- phase1_cdr/` → empty (Phase 1 frozen).
- **CAVEAT:** the pandas-dependent suite (`tests/phase2a`) could NOT run on the dev machine — pandas'
  compiled `tslib` DLL is blocked by a Windows Application Control / Smart App Control policy
  (`ImportError: ... An Application Control policy has blocked this file`). This is a machine
  environment issue, not a code issue. Pushed so **CI (Ubuntu) runs the full suite** as the real gate.

### For Codex / next
- Review the branch diff; the logging change is the only behavioural surface (additive).
- Not merged — Nadim merges. Phase 3 remains parked.

## 2026-06-30 - Claude: DB migration seam MERGED to main; session close

Nadim authorized the merge. `main` fast-forwarded `fa54bce → 9fc4c6a` and pushed to origin; both
`claude/migration-seam` and `codex/migration-seam-review` pruned (neither was on origin). Post-merge
on `main`: **136 passed** (`tests/phase2a tests/architecture phase1_cdr/tests`), `phase1_cdr/`
byte-frozen. The two-agent review trail for this seam is the entries below (build → review → fix#1 →
re-review → fix#2 → CLEAR).

**Pre-Phase-3 runway is complete.** The migration seam was the last genuinely-missing structural
piece; every seam Phase 3 needs is now in place and CI-guarded.

### Open items for next session (none blocking)
- **Phase 3 first move:** wire migrate-on-login — one line `migrations.migrate(g.db)` in
  `app/api/guards.py:get_db()`, right after `storage.connect(key)` and before storing `g.db`
  (ADR 0002). Then the larger Phase 3 work: auth de-globalization (`DB_KEY`/`USERNAME` →
  per-session), multi-account, RBAC/sessions.
- **Non-blocking nit (Codex):** `_normalize_ddl` (`" ".join(sql.split())`) is not quote-aware.
  Harmless now (baseline has no triggers/views/quoted DEFAULT/CHECK bodies); make it quote-aware
  when migration 2+ adds such an object whose body has significant whitespace.
- **Orthogonal, still open:** Codex's `codex/github-security-foundation` PR #11
  (CODEOWNERS/SECURITY.md/dependabot/CI perms) — independent of this work; merge at will.

## 2026-06-30 - Codex: re-review of trigger/view fingerprint fix on `codex/migration-seam-review` - CLEAR WITH NIT

Reviewed `claude/migration-seam` at `a2d4191` (linear on top of Codex re-review
`1df207c`). I fast-forwarded `codex/migration-seam-review` to `a2d4191` and added
only this handoff entry. No merge to `main` performed.

### Finding
- **NIT - `_normalize_ddl` is not quote-aware for future trigger/view/default bodies**
  (`app/infra/migrations.py:112`). `" ".join(sql.split())` collapses whitespace
  inside string literals and quoted identifiers too, so two semantically different
  future baseline objects could compare equal if the only textual difference is
  repeated whitespace inside a literal/name (for example `'a  b'` versus `'a b'`).
  This is not a blocker for the current migration seam: the v1 baseline has no
  triggers/views and no string-literal defaults, and the fixed trigger/view exploit is
  rejected by the unexpected object name before body comparison matters. If a future
  migration adds baseline triggers, views, generated expressions, CHECK/default string
  literals, or quoted identifiers where internal whitespace is meaningful, replace
  this with a quote-aware normalizer or compare SQLite-stored SQL more conservatively.

### Checks
- `git fetch --all`
- `git log --oneline 1df207c..claude/migration-seam` -> just
  `a2d4191 claude: fingerprint all schema objects, incl. triggers and views`.
- `git diff 1df207c..claude/migration-seam`
- Read the top `HANDOFF.md` entry for the fix.
- Extra-trigger v0 probe (exact `_BASELINE` plus `CREATE TRIGGER t_extra AFTER INSERT
  ON datasets BEGIN UPDATE datasets SET name = name; END;`) -> raises
  `SchemaMismatchError`, reports `unexpected=['t_extra']`, and leaves
  `user_version == 0`.
- Extra-view v0 probe (exact `_BASELINE` plus `CREATE VIEW v_extra AS SELECT id FROM
  datasets`) -> raises `SchemaMismatchError`, reports `unexpected=['v_extra']`, and
  leaves `user_version == 0`.
- Clean Phase-2A v0 probe (execute `_BASELINE`, commit, `user_version == 0`) ->
  `_schema_fingerprint(conn) == _baseline_fingerprint()` is true, adoption returns 1,
  and `user_version == 1`.
- Clean baseline `sqlite_master` rows include only the named user index plus the five
  tables in the fingerprint. `sqlite_autoindex_targets_1` exists as `type='index'`
  with `sql IS NULL` and is excluded; no SQLCipher/SQLite internal object leaked into
  the fingerprint.
- Object-surface review: persistent main-schema SQLite objects are covered through
  `sqlite_master` rows with stored SQL. `WITHOUT ROWID`, generated columns, `STRICT`,
  collations in column/index DDL, constraints, virtual tables, and virtual-table shadow
  tables all surface through table/index DDL rows and therefore differ from the
  baseline. Attached DBs and TEMP objects are per-connection/non-main-schema state, not
  persistent adoptable schema in the encrypted DB file. I did not find another
  persistent schema bypass.
- `.venv\Scripts\python.exe -m pytest tests\phase2a\test_migrations.py` -> **11 passed**.
- `.venv\Scripts\python.exe -m pytest tests\phase2a tests\architecture phase1_cdr\tests`
  -> **136 passed**.
- `.venv\Scripts\ruff.exe check app tests main.py` -> clean.
- `git diff --stat main -- phase1_cdr` -> empty.

### Verdict
No blockers. The trigger/view exploit is dead, clean v0 adoption still works, and the
object set is complete for persistent main-schema adoption. Ready for Nadim to merge
`claude/migration-seam` if he accepts the non-blocking normalization nit above.

## 2026-06-30 - Claude: fingerprint now covers triggers/views on `claude/migration-seam` - FOR RE-REVIEW

Addresses Codex's second BLOCKER below (`1df207c`). The full-DDL fingerprint fixed the
weaker-constraints case but `_schema_fingerprint` still filtered `type IN ('table','index')`, so a
v0 DB with exact baseline tables/index PLUS an extra `CREATE TRIGGER`/`CREATE VIEW` was accepted
and stamped v1 — and a trigger can change future writes. Agreed; fixed. Sits linearly on top of
Codex's re-review (build `d4ef3a1` → review `ca564e6` → fix `6be5dad` → re-review `1df207c` → this).

### Fix
- `app/infra/migrations.py`: `_schema_fingerprint` now selects every user-defined object via
  `WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'` (drops the `type IN (...)` filter), so
  tables, indexes, **triggers, and views** are all compared. `sql IS NOT NULL` still excludes
  `sqlite_autoindex_*` (their UNIQUE is captured in the owning table's DDL). Exact-equality against
  the in-memory baseline (which has no triggers/views) therefore rejects any extra object.
- `tests/phase2a/test_migrations.py`: added `test_rejects_v0_with_extra_trigger` (Codex's exact
  case) and `test_rejects_v0_with_extra_view`; both assert `SchemaMismatchError` + `user_version`
  stays 0.
- ADR 0002: guard description now lists tables/indexes/triggers/views.

### Verification
- `pytest tests/phase2a tests/architecture phase1_cdr/tests` → **136 passed** (was 134; +2).
- `ruff check app tests main.py` → clean. `git diff --stat main -- phase1_cdr/` → empty.
- `lint-imports` CI-only (no win_arm64 grimp wheel); no import changes since the prior fix.

### What's left
- Codex re-review; then Nadim merges. Migrate-on-login still intentionally unwired (Phase-3 flip in
  `app/api/guards.py:get_db()`, per ADR 0002).

## 2026-06-30 - Codex: re-review of fingerprint fix on `codex/migration-seam-review` - BLOCKER

Reviewed `claude/migration-seam` at `6be5dad` (linear on top of Codex review
`ca564e6`). I fast-forwarded `codex/migration-seam-review` to the reviewed fix
commit and added only this handoff entry. No merge to `main` performed.

### Finding
- **BLOCKER - v0 adoption still ignores extra persistent schema objects**
  (`app/infra/migrations.py:115`, `app/infra/migrations.py:119`).
  The original same-columns/weaker-constraints exploit is fixed, but the new
  fingerprint query only reads `sqlite_master` rows where `type IN ('table',
  'index')`. A v0 DB with the exact baseline tables and `idx_records_dataset_phone`
  plus an extra persistent `CREATE TRIGGER` or `CREATE VIEW` has the same
  fingerprint, so `migrations.migrate(conn)` accepts it, runs migration 1, and
  stamps `user_version = 1` while leaving the extra object in place. That still
  violates the "adopt only the exact v1 baseline" safety claim; an extra trigger
  can change future writes and migration 1 cannot repair/remove it. Suggested fix:
  fingerprint every persistent user schema object with non-null SQL, excluding
  SQLite internals (`sqlite_%` autoindexes/tables), and key by object type + name
  before comparing to the baseline. Add regression coverage for at least an
  extra trigger; extra view is the same blind spot unless views are deliberately
  allowed and documented.

### Checks
- `git fetch --all`
- `git log --oneline ca564e6..claude/migration-seam` -> just
  `6be5dad claude: strengthen v0 adoption guard to full-DDL fingerprint`.
- `git diff --stat ca564e6..claude/migration-seam` -> 4 files:
  `HANDOFF.md`, `app/infra/migrations.py`, ADR 0002, and
  `tests/phase2a/test_migrations.py`.
- Read the top `HANDOFF.md` entry for the fix.
- Same-columns/weaker-constraints v0 probe -> now raises `SchemaMismatchError`
  and leaves `user_version == 0`.
- Legacy Phase-2A v0 probe (execute `_BASELINE`, commit, `user_version == 0`)
  -> `_schema_fingerprint(conn) == _baseline_fingerprint()` is true; adoption
  returns 1 and leaves `user_version == 1`. No false rejection for the old
  `init_schema` shape; `IF NOT EXISTS` and the named index canonicalize the same
  on the keyed on-disk SQLCipher connection and the in-memory SQLCipher reference.
- Extra table and extra index probes -> correctly reject with
  `SchemaMismatchError` and leave `user_version == 0`.
- Extra trigger and extra view probes -> incorrectly accepted and stamped
  `user_version == 1`.
- `_normalize_ddl = " ".join(sql.split())` is adequate for the app-created
  baseline path because both sides are produced by the same SQLCipher engine from
  the same DDL. It can false-reject semantically equivalent hand-written schemas
  with different quoting/case/comments, but that is acceptable for this adoption
  guard if the contract is "old app-created Phase-2A DB only".
- `migrations.py` importing `sqlcipher3` is not a layering issue: infra -> external
  is allowed, and the Phase-1 forbidden contract only forbids direct
  `detection`/`loader` imports.
- `.venv\Scripts\python.exe -m pytest tests\phase2a\test_migrations.py tests\phase2a\test_storage.py tests\phase2a\test_auth.py tests\phase2a\test_account.py`
  -> **34 passed**.
- `.venv\Scripts\python.exe -m pytest tests\phase2a tests\architecture phase1_cdr\tests`
  -> **134 passed**.
- `.venv\Scripts\python.exe -m ruff check app tests main.py` -> clean.
- `git diff --stat main -- phase1_cdr` -> empty.
- Local `lint_imports` not run: `.venv` has no `lint_imports` module installed,
  matching the known local import-linter limitation.

## 2026-06-30 - Claude: fixed Codex's fingerprint BLOCKER on `claude/migration-seam` - FOR RE-REVIEW

Addresses the BLOCKER in Codex's review below (`ca564e6`). Codex cleared atomicity but proved the
v0 adoption guard only compared table + column **names**, so a same-columns DB with weaker
constraints (no NOT NULL / FK / UNIQUE, missing index) was accepted and stamped v1 — which
migration 1's `IF NOT EXISTS` can't repair. Agreed; fixed. This commit sits on top of Codex's
review commit (linear: build `d4ef3a1` → review `ca564e6` → this fix).

### Fix
- `app/infra/migrations.py`: replaced the column-name set check with a **full-DDL fingerprint**.
  `_schema_fingerprint(conn)` reads `sqlite_master.sql` for every user table+index and normalizes
  whitespace; `_baseline_fingerprint()` computes the expected map from a throwaway in-memory
  `sqlcipher.connect(":memory:")` running `_BASELINE`, so SQLite canonicalizes both sides (no
  hand-maintained constants). `_assert_matches_baseline` now requires exact equality — rejects
  missing, drifted (weaker constraints), AND extra objects. Removed `_V1_FINGERPRINT`.
- `tests/phase2a/test_migrations.py`: new `test_rejects_v0_with_same_columns_but_weaker_constraints`
  reproduces Codex's exact case (all 5 tables, same columns, no constraints/index) → asserts
  `SchemaMismatchError` and `user_version` stays 0.
- ADR 0002: guard description updated to spell out full-DDL fingerprinting.

### Verification
- `pytest tests/phase2a tests/architecture phase1_cdr/tests` → **134 passed** (was 133; +1).
- `ruff check app tests main.py` → clean. `git diff --stat main -- phase1_cdr/` → empty.
- `lint-imports` CI-only (no win_arm64 grimp wheel). migrations.py now imports the external
  `sqlcipher3` driver for the in-memory reference — no app-layer/Phase-1 import added, so the
  forbidden + layers contracts are unaffected.

### What's left
- Codex re-review of the fingerprint fix; then Nadim merges. Migrate-on-login still intentionally
  unwired (Phase-3 flip in `app/api/guards.py:get_db()`, per ADR 0002).

## 2026-06-30 - Codex: DB migration seam review on `codex/migration-seam-review` - BLOCKER

Reviewed `claude/migration-seam` at `d4ef3a1` against `main`. No merge performed.
Verdict: **BLOCKER before merge** because the v0 adoption fingerprint is weaker than
the safety claim in ADR 0002/HANDOFF.

### Findings
- **BLOCKER - v0 adoption accepts same-column drift it cannot repair**
  (`app/infra/migrations.py:84`, `app/infra/migrations.py:121`). `_assert_matches_baseline`
  compares only expected table names plus column-name sets from `PRAGMA table_info`. That catches
  missing tables and missing/extra columns, but it accepts a v0 database whose tables have the
  same column names while losing `NOT NULL`, `REFERENCES ... ON DELETE CASCADE`, and
  `UNIQUE(dataset_id, phone_number)` constraints. Migration 1 uses `CREATE TABLE IF NOT EXISTS`,
  so those table constraints are not repaired after adoption, yet the DB is stamped v1. I proved
  this with an isolated SQLCipher DB: created all five baseline tables with the same column names
  but no FKs/NOT NULL/UNIQUE/indexes, then `migrations.migrate(conn)` returned 1 and left
  `PRAGMA foreign_key_list(cdr_records)` and `PRAGMA index_list(targets)` empty. A legitimate
  Phase-2A DB should pass a stronger fingerprint; this drifted DB should not. Suggested fix:
  fingerprint richer schema metadata (`PRAGMA table_info` type/notnull/pk, `foreign_key_list`,
  `index_list`/`index_info`, and/or normalized `sqlite_master.sql` for the baseline objects) and
  add a regression test for same-column/weaker-constraint drift.
- **NIT - atomic rollback test is broad and underspecifies the exception**
  (`tests/phase2a/test_migrations.py:81`). The bad-v2 test genuinely proves DDL rollback for
  `_probe` and the final version stays at 1, but `pytest.raises(Exception)` should be narrowed
  to the SQLCipher/SQLite operational error it intentionally triggers. I also ran a supplemental
  probe with `PRAGMA user_version = 2` inside the failing v2 body before the duplicate table
  statement; SQLCipher rolled the version write back to 1, so the underlying atomicity claim is
  sound.
- **NIT - public/private baseline naming**
  (`app/infra/storage.py:16`). Having migration 1 own the baseline is the right direction; moving
  the baseline back to `storage.py` would either create a circular dependency or make the migration
  seam depend on storage. The only cleanup I would make is exporting a public
  `BASELINE_SCHEMA_SQL`/`BASELINE_DDL` from `migrations.py` and re-exporting that as
  `storage.SCHEMA_SQL`, rather than reaching into `_BASELINE`.
- **NIT - COLLAB architecture list is now stale.** `COLLAB.md` still lists infra as
  `config/crypto/storage/phase1`; add `infra.migrations` there so future agents see the same
  boundary model that `pyproject.toml` now enforces.

### Checks that look good
- **Atomicity:** `conn.executescript("BEGIN IMMEDIATE; ... PRAGMA user_version=N; COMMIT;")`
  behaves atomically under this SQLCipher driver. `executescript()` commits any pending transaction
  before the script, but the explicit `BEGIN IMMEDIATE` owns the migration transaction. On failure,
  the transaction remains rollbackable; if no transaction remains, the defensive rollback swallow
  is acceptable. A supplemental probe confirmed both DDL and `user_version` writes roll back.
- **Behavior freeze for current callers:** production still reaches `init_schema()` only from
  account creation; request-path `get_db()` remains `storage.connect(key)` only. Fresh init creates
  the same baseline schema, stamps `user_version == 1`, and leaves `conn.in_transaction == False`.
  No observable change for current callers beyond the version stamp. Caveat: calling
  `init_schema()` as a no-op on an already-v1 DB with unrelated pending DML no longer acts like the
  old unconditional `executescript(...); commit()` commit hammer, but no current caller relies on
  that pattern.
- **Import-linter shape:** adding `app.infra.migrations` to the Phase-1 forbidden source list is
  the right contract update. The layered contract already has `app.infra` as the bottom package, so
  `storage -> migrations` is infra-internal and should keep the layer contract green.
- **Phase 3 readiness:** the documented migrate-on-login flip location is right: call
  `migrations.migrate(g.db)` in `app/api/guards.py:get_db()` immediately after `storage.connect(key)`
  and before caching `g.db`, so it runs before any route-owned transaction.

### Verification
- `git fetch --all`
- `git log --oneline main..claude/migration-seam` -> `d4ef3a1 claude: build the DB migration seam (infra/migrations.py)`
- `git diff main...claude/migration-seam`
- Read the top `HANDOFF.md` entry for `claude/migration-seam`.
- SQLCipher probes:
  - failing v2 with `_probe`, `PRAGMA user_version = 2`, duplicate `_probe` -> raised
    `OperationalError`, final `user_version == 1`, `_probe` absent.
  - same-column/weaker-constraint v0 schema -> incorrectly accepted and stamped v1.
  - fresh `storage.init_schema()` -> `user_version == 1`, `conn.in_transaction == False`.
- `.venv\Scripts\python.exe -m pytest tests\phase2a\test_migrations.py tests\phase2a\test_storage.py tests\phase2a\test_auth.py tests\phase2a\test_account.py`
  -> **33 passed**.
- `.venv\Scripts\python.exe -m pytest tests\phase2a tests\architecture phase1_cdr\tests`
  -> **133 passed**.
- `.venv\Scripts\python.exe -m ruff check app tests main.py` -> clean.
- `git diff --stat main -- phase1_cdr` -> empty.
- Local `lint-imports` not run: this venv has no `lint_imports` module installed, matching the
  known local grimp/import-linter limitation; rely on CI for that gate.

## 2026-06-30 - Claude: DB migration seam on `claude/migration-seam` - FOR REVIEW (do NOT merge)

Pre-Phase-3 runway, behavior-frozen like the modular reorg. Builds the one missing structural
seam: ADR 0001 claimed `infra/migrations.py` "the seam is ready" but it never existed — schema
was inline `CREATE TABLE IF NOT EXISTS` with no version tracking, so the first Phase 3 schema
change would have no upgrade path for an installed encrypted DB.

### What changed
- **New `app/infra/migrations.py`** — versioned runner keyed on `PRAGMA user_version` (encrypted
  DB header, no extra table). `_BASELINE` = the old `storage.SCHEMA_SQL` moved verbatim;
  `MIGRATIONS = [(1, _BASELINE)]`. `migrate(conn, migrations=MIGRATIONS)` applies pending
  migrations, each with DDL + version bump in one `BEGIN IMMEDIATE … COMMIT` (ROLLBACK on
  exception — atomicity fix per Codex review). Two guards: `SchemaTooNewError` (user_version >
  latest), `SchemaMismatchError` (a v0 DB adopted only if it matches the baseline fingerprint;
  drifted/partial DB fails loudly instead of being stamped v1).
- **`app/infra/storage.py`** — removed inline `SCHEMA_SQL` (kept as a `= migrations._BASELINE`
  re-export for back-compat); `init_schema(conn)` now delegates to `migrations.migrate(conn)`.
  `connect()` untouched. Only new observable on fresh install: `user_version == 1`.
- **`pyproject.toml`** — added `app.infra.migrations` to the Phase-1 `forbidden` import-linter
  contract (parity with config/crypto/storage).
- **`tests/phase2a/test_migrations.py`** (new, 8 tests) — fresh / idempotent / v0-adoption /
  drift-guard / schema-too-new / atomic-rollback / forward-migration / contiguity.
- **Docs** — ADR 0002 (this seam); ADR 0001 "Defers" line updated (seam built, not "ready").

### Verification
- `pytest tests/phase2a tests/architecture phase1_cdr/tests` → **133 passed** (was 125; +8).
- `ruff check app tests main.py` → clean.
- `git diff --stat main -- phase1_cdr/` → empty (Phase 1 frozen).
- `lint-imports` NOT run locally (grimp has no win_arm64 wheel — runs in CI `boundaries`). The
  contract change only adds a forbidden-source module that imports no Phase-1 module and adds no
  cross-layer import, so it is expected green.

### What's left / notes
- Nadim reviews + merges; Codex review welcome (its plan-stage review is already folded in:
  atomicity, schema-too-new guard, v0 fingerprint guard, exact migrate-on-login flip location).
- **Migrate-on-login is intentionally NOT wired** (keeps this behavior-frozen). Phase-3 one-line
  flip: `migrations.migrate(g.db)` in `app/api/guards.py:get_db()` after `storage.connect(key)`,
  before storing `g.db`. Documented in ADR 0002. Consequence today: fresh DBs are stamped at
  account creation; an existing pre-versioning DB is adopted only on the next explicit
  `init_schema`/`migrate` call, not automatically on login.
- Orthogonal to Codex's `codex/github-security-foundation` (PR #11) — no shared files; either can
  merge first.

## 2026-06-30 - Codex: GitHub security foundation on `codex/github-security-foundation` - PR #11 OPEN

Nadim asked whether GitHub security/governance should be enabled before scaling the
project to an enterprise, multi-user platform. I checked the local repo and the
authenticated GitHub access. `gh` is logged in as `cook-with-claude`, and that
account has `ADMIN` permission on `cook-with-claude/La-Passion`. Repo is private,
default branch is `main`.

### What changed
- Created branch `codex/github-security-foundation` from `main`.
- Committed and pushed `894d698` (`Add GitHub security foundation`).
- Opened draft PR #11:
  `https://github.com/cook-with-claude/La-Passion/pull/11`.
- Added `.github/CODEOWNERS` so security-sensitive paths have explicit ownership
  once GitHub branch protection/rulesets can enforce code-owner review. Current
  owner is `@cook-with-claude`; protected paths include `app/auth/`, `app/api/`,
  `app/audit/`, `app/infra/crypto.py`, `app/infra/storage.py`, `.github/`,
  dependency files, `constraints.txt`, and `pyproject.toml`.
- Added `SECURITY.md` with a private vulnerability reporting policy, supported-version
  note for the pre-release project, requested report contents, and a 3-business-day
  acknowledgement target.
- Updated `.github/dependabot.yml` to add root pip Dependabot coverage for the
  Phase 2A/main app dependencies. Existing `/phase1_cdr` pip and GitHub Actions
  Dependabot coverage remains unchanged.
- Updated `.github/workflows/ci.yml` with default workflow token permissions:
  `contents: read`.
- Directly enabled the repository setting `delete_branch_on_merge=true` on GitHub.

### GitHub security state observed
- Dependabot alerts/security updates are enabled; current Dependabot alert count was `0`.
- Branch protection/rulesets could not be enabled/read on this private repo: GitHub API
  returned "Upgrade to GitHub Pro or make this repository public to enable this feature."
- CodeQL/code scanning could not be enabled through the API because code scanning is
  not enabled/available for this private repo yet. User-facing next step is repo
  Settings -> Advanced Security -> CodeQL analysis -> Set up -> Default, but it may
  require GitHub Code Security/GitHub Pro for this private repo.
- Private vulnerability reporting was not available through the repo API in this session.

### Verification
- `git diff --check -- .github/dependabot.yml .github/workflows/ci.yml .github/CODEOWNERS SECURITY.md`
  before commit -> clean.
- Staged only `.github/dependabot.yml`, `.github/workflows/ci.yml`, `.github/CODEOWNERS`,
  and `SECURITY.md`; left unrelated untracked `.claude/`, `sample_cdr_data.xlsx`, and
  `session-logs/` untouched.
- Verified PR #11 is open and draft, base `main`, head `codex/github-security-foundation`.

### What's left
- Nadim reviews/merges PR #11 if he wants these repo-governance files on `main`.
- If/when the GitHub plan supports it, enable branch protection/rulesets on `main`:
  require PRs, CI, code-owner review, conversation resolution, no force pushes/deletes.
- If/when CodeQL is available, enable default setup first for Python, JavaScript, and
  GitHub Actions; triage initial alerts before making CodeQL required.

## 2026-06-30 - Codex: dependency lock review on `codex/dep-lock-review` - CLEAR WITH NOTE

Reviewed `origin/claude/dep-lock` at `11e9b4e` against `main`/`origin/main`
(`02d9eab`). No merge performed. Verdict: **CLEAR** for Nadim to fast-forward
merge the Claude branch; no blocking dependency-lock findings.

### Review checks
- **Shared lock / wheels:** PyPI metadata check over all 27 `constraints.txt` pins for
  Linux x64 CPython 3.11 and 3.12. All native/heavy pins have compatible wheels on both
  versions, including `numpy==2.4.6` (`cp311` and `cp312` manylinux_2_27/_2_28),
  `pandas==3.0.3`, `cffi==2.0.0`, `cryptography==49.0.0`, `bcrypt==5.0.0`,
  `MarkupSafe==3.0.3`, and `sqlcipher3-wheels==0.5.7`.
- **Wheel note:** `proxy_tools==0.1.0` is the only pin without a wheel on either Python
  version; PyPI publishes only `proxy_tools-0.1.0.tar.gz`. It is an unconditional
  `pywebview==6.2.1` dependency, but the sdist is tiny pure Python (`proxy_tools`
  package only, no native extension or install requirements), and CI installed it
  successfully. I do not consider this a blocker; it just means the lock is not strictly
  wheel-only.
- **Phase 1 constraints path:** the `test` job's `defaults.run.working-directory` is
  `phase1_cdr`, so `pip install -r requirements.txt -c ../constraints.txt` reaches the
  root lock without editing the frozen Phase 1 tree. `git diff --stat
  main...origin/claude/dep-lock -- phase1_cdr/` is empty.
- **Unpinned dev tools:** leaving `ruff` and `import-linter` unpinned is acceptable for
  this runtime lock. The risk is future CI-gate drift, not runtime drift; if we later want
  fully reproducible tooling too, add a separate dev/tool lock.
- **Phase 1 numpy floor:** Phase 1 does not import numpy directly; pandas pulls it for
  typed loading, timestamp parsing, grouping, and deterministic sorted tallies. The 3.12
  CI `test` job installs Phase 1 with the root constraints file, so its green unit tests
  and ground-truth harness are the right evidence that forcing numpy 2.5.0 -> 2.4.6 is
  inert for current outputs.

### Verification
- `git fetch --all`
- `git diff main...origin/claude/dep-lock -- constraints.txt .github/workflows/ci.yml requirements.txt`
- `gh run view 28455501879 --repo cook-with-claude/La-Passion --json ...` -> success
  at `00dda941fab87e644f6ea1588a3ec9b5191ea908`; `test`, `phase2a`, `boundaries`, and
  `frontend` all succeeded.
- PyPI wheel-tag metadata script for every pin on CPython 3.11 and 3.12/Linux x64 -> only
  `proxy_tools==0.1.0` reported `sdist-only`; all other pins matched wheels.
- `.venv\Scripts\python.exe -m pytest tests/phase2a tests/architecture phase1_cdr/tests`
  -> **125 passed** locally on Python 3.11.9 with `numpy==2.4.6`, `pandas==3.0.3`.
- From `phase1_cdr/`: `..\.venv\Scripts\python.exe main.py sample_data.csv
  ground_truth.json` equivalent run -> **34/34 passed (100%)**.

### What's left
- Nadim ff-merge `claude/dep-lock` into `main` if he accepts the non-blocking
  `proxy_tools` sdist note; then prune the Claude/Codex review branches.

## 2026-06-30 — Claude: dependency lock on `claude/dep-lock` — FOR REVIEW (do NOT merge)

Closes the last open Step-0 follow-up (ADR 0001): the runtime dependency stack was
**unpinned**, so CI/local installs picked up whatever was latest — the drift class that
produced the bcrypt-5.0 silent-truncation→ValueError surprise earlier in the project.
Branched off `main` (`02d9eab`, the merged reorg). **No app/test code changes** — only the
lock + CI wiring, so the suite is unchanged from `main` (125).

### What landed
- **`constraints.txt`** (new) — full runtime lock (direct + transitive, 27 pins). **Generated
  from `pip freeze` in CI** on ubuntu x64 / Python 3.11 (the Phase 2A job resolves a superset
  of Phase 1's deps), not from the win_arm64 dev venv (wrong wheels). `numpy==2.4.6` is the
  shared floor — 3.11 resolves 2.4.6, 3.12 would pick 2.5.0; 2.4.6 has wheels for both.
- **`.github/workflows/ci.yml`** — all three Python jobs now install with `-c constraints.txt`
  (Phase 1 via `-c ../constraints.txt` from its `phase1_cdr/` working dir — **the frozen
  `phase1_cdr/` tree is untouched**; only the workflow command changed). The SAME locked set is
  thus exercised on **both 3.11 (Phase 2A) and 3.12 (Phase 1)**. Dev tools (ruff/import-linter)
  intentionally left unpinned.
- **`requirements.txt`** — header pointing local installs at the lock; direct deps stay loose
  (the plan wanted a constraints/lock, not a hand-pinned requirements.txt).

### How the lock was produced + validated (the plan's "both CI jobs" requirement)
A temp commit printed `pip freeze` in both the 3.11 and 3.12 jobs; the only cross-version
conflict was numpy (2.4.6 vs 2.5.0), resolved to the shared 2.4.6 floor. Temp steps removed,
lock wired in, then **CI re-run all green on the locked set** (run 28455501879 @ `00dda94`):
`test` ✓ (Phase 1 3.12 — the **ground-truth validation harness passed**, so numpy 2.5.0→2.4.6
is inert) · `phase2a` ✓ · `boundaries` ✓ · `frontend` ✓.

### What's left
- **Codex review** of `origin/claude/dep-lock` (`git diff main...origin/claude/dep-lock` — 3
  files), then **Nadim ff-merge** (clean — `main` is an ancestor), then prune the branch.
- Regeneration note (in `constraints.txt`): after an intentional dep bump, re-run the `pip
  freeze` capture (it's in this branch's git history) and update the lock; CI re-validates both.

## 2026-06-30 - Codex: modular-monolith reorg Steps 1-9 review on `codex/modular-reorg-review` - CLEAR

Reviewed `origin/claude/modular-reorg-impl` at `5037697` against `main` (`bb9d7b2`). No merge
performed. Verdict: **CLEAR** for Nadim to merge the Claude branch (or this Codex review branch if
you want the review note carried with it). I found no behavior-freeze blockers.

### Review checks
- **Moved SQL / bind order:** mechanically extracted and spot-diffed the SQL calls from the original
  `app/imports.py`, `app/targets.py`, and `app/analysis.py` against `app/datasets/repo.py`,
  `app/targets/repo.py`, and `app/analysis/repo.py`. SQL strings, operation order, and bind order
  match. The renamed repo parameters are still passed in the same tuple/dict order by the routes.
- **Transaction ownership:** repos do not commit or roll back. Routes still own the unit-of-work:
  repo calls -> `audit.write_audit(...)` -> `db.commit()`, with the target insert race still caught in
  `app/targets/routes.py` via `sqlcipher.IntegrityError`, followed by route-level `db.rollback()` and
  the same 409 response.
- **Step 5 characterization tests:** the audit-failure tests genuinely pin rollback-on-failed-audit
  for import, dataset delete, and analysis. The duplicate-target clean-connection test pins the
  non-race 409 path; the existing race test patches `app.targets.routes.get_db`, and its synthetic
  `IntegrityError` is raised by `repo.insert_target(...)`, so the repo extraction is exercised.
- **Layering / import-linter:** the four contracts in `pyproject.toml` match ADR 0001's as-built
  dependency model. I agree with dropping the separate containers contract: the global module-level
  layers contract already places every `*.routes` module above every `*.repo` module. `app.api` is
  correctly split at module level (`system` as APPLICATION; responses/guards/errors as SUPPORT).
- **`current_username()`:** all production audit call sites in auth/imports/targets/analysis now go
  through the accessor. Its body preserves the current process-global read (`current_app.config["USERNAME"]`);
  auth logout/change-password call it only after `login_required`, and `USERNAME` is initialized by
  `create_app()`, so this is equivalent to the current supported runtime state.
- **Phase 1 seam:** production app code reaches Phase 1 only through `app/infra/phase1.py`; both
  `app/datasets/validation.py` and `app/analysis/bridge.py` import through that seam. The remaining
  direct `phase1_cdr` references are tests/regression oracles, not app code. Phase 1 diff stat is empty.
- **AST boundary tests:** not vacuous: they assert at least one route and repo file exists, then scan
  all `app/*/routes.py` and `app/*/repo.py`. They are intentionally narrow (SQL execution in routes,
  commit/rollback in repos, Flask imports in repos), which is fine because import-linter covers the
  import-direction contracts.

### Verification
- `.venv\Scripts\python.exe -m pytest tests/phase2a tests/architecture phase1_cdr/tests` -> **125 passed**.
- `git diff --stat main -- phase1_cdr/` -> empty.
- Note: plain global `pytest` used the wrong Python environment and failed collection on missing
  `flask` / `sqlcipher3`; the repo `.venv` is the valid local verification environment.

### What's left
- Nadim merge only. No Codex code changes beyond this `HANDOFF.md` review entry.

## 2026-06-30 — Claude: modular-monolith reorg **Steps 1–9** on `claude/modular-reorg-impl` — FOR REVIEW (do NOT merge)

Executed the full behavior-frozen backend reorganization (ADR 0001; plan
`~/.claude/plans/discussion-only-ancient-whistle.md`). **Step 0 was first ff-merged to
`main` (Nadim-authorized this session; tip `bb9d7b2`)** and the redundant `passwords`
branch pruned. Then Steps 1–9 were built on a fresh branch off `main`, **one commit per
step**, suite green + Phase 1 byte-frozen between every step. Per COLLAB this is for Codex
review — **only Nadim merges.**

### What landed (one commit per step; `git log --oneline main..claude/modular-reorg-impl`)
- **Step 1 (`74e9726`)** `app/infra/` — moved `config`/`crypto`/`storage`; new `infra/phase1.py`,
  the single owned seam to frozen `phase1_cdr` (deleted the duplicated `sys.path` blocks in
  `validation.py` + `detection_bridge.py`).
- **Step 2 (`86c104f`)** `app/api/` — `responses` (ok/err/json_body), `guards` (login_required,
  get_db, **new `current_username()`** accessor), `errors` (register_error_handlers), `system`
  (/api/health + /api/status as a blueprint — identical URLs). `app/__init__.py` shrank to the
  factory; routes read identity via `current_username()` (one function for Phase 3 to swap).
- **Step 3 (`01e4bdc`)** `app/auth/` — `account.py` + `routes.py` (atomic).
- **Step 4 (`f1c3d54`)** `app/audit/` — `audit.py` → `audit/log.py` (atomic).
- **Step 5 (`d73889a`)** characterization tests — pinned the route-owned txn contract
  (audit-failure rolls back import/analysis/delete; dup-target 409 leaves the conn clean)
  BEFORE extraction. 117 → 121.
- **Steps 6–8 (`bcca51a`,`ee73289`,`858494c`)** `app/datasets/`, `app/targets/`, `app/analysis/`
  + per-domain `repo.py` extraction. Routes own the unit-of-work and never write SQL; repos
  take a `conn`, return dicts, never commit. `tests/architecture/test_boundaries.py` (generic
  AST scanners) added in Step 6 → 121 → 125. `app/` now holds only `create_app()` + `ui.py`.
- **Step 9 (`186e2ad`, `70c0d55`)** enforcement: 4 **import-linter** contracts (enforcing) in
  `pyproject.toml` — layered architecture, domain independence, Phase-1-only-via-infra.phase1,
  repos-import-neither-audit-nor-api; new CI **`boundaries`** job (ruff + lint-imports) on
  ubuntu x64; `phase2a` job also runs `tests/architecture`. `3c25cc1` enabled ruff isort (`I`)
  and sorted every import block. ADR/CLAUDE.md updated to as-built.

### Verification
- **Per step:** `pytest tests/phase2a tests/architecture phase1_cdr/tests` green (117 → **125**);
  `git diff --stat main -- phase1_cdr/` **empty** at every step (Phase 1 byte-frozen).
- **ruff** (incl. `I`) clean. **CI all green** on the branch tip `70c0d55` (run 28449298650:
  test ✓ phase2a ✓ frontend ✓ boundaries ✓).
- **import-linter validated with deliberate bad imports** (the plan's requirement). grimp has
  no win_arm64 wheel so it can't run on the dev machine; validated in CI instead: a throwaway
  branch with one violation per contract made **all 4 contracts report BROKEN** with the right
  messages (e.g. `app.analysis.repo is not allowed to import app.audit`;
  `app.datasets is not allowed to import detection`; `app.targets … import app.datasets`;
  `app.audit … import app.datasets.repo`). Throwaway branch deleted (local + origin).

### Notes / deviations from the plan
- **No `containers` contract.** The global `layers` contract already places every
  `<domain>.routes` above every `<domain>.repo`, so routes-above-repo is covered without a
  separate per-domain `containers` contract. Documented in ADR 0001.
- **CI caught a real contract bug** (the deliberate-validation value): import-linter needs
  `include_external_packages=true` at the **top level** (not per-contract) when a forbidden
  contract names external modules (detection/loader). Fixed in `70c0d55`.
- **Dependency lock/pinning** (a Step-0 sub-item) is still **NOT done** — flagged in the Step 0
  entry below as a focused CI follow-up; out of scope for this structural reorg.
- Blueprint internal names kept (`imports`/`targets`/`analysis`/`auth`) so endpoint names and
  all HTTP responses are byte-identical.

### What's left
- **Codex review** of `origin/claude/modular-reorg-impl` (`git diff main...origin/claude/modular-reorg-impl`;
  the per-step commits make granular review easy), then **Nadim merge** (clean ff — `main` is an
  ancestor). After merge, prune the branch.
- **First Phase 3 increment** (per ADR 0001 Part C): de-globalize auth — multi-account
  `auth/account.py` + `auth/session.py` per-session identity/key context; `current_username()`
  (added now) swaps to read it. The structure is ready for it.

## 2026-06-30 — Claude: modular-monolith reorg **Step 0** (conventions + tooling) on `claude/modular-reorg-step0` — FOR REVIEW (do NOT merge)

Kicks off the Nadim-approved pre-Phase-3 reorganization of the backend into a **layered modular
monolith** (full plan + rationale in ADR `docs/adr/0001-modular-monolith.md`; Phase 3 =
multi-user/admin/LAN, so the current process-global auth state + single-account model must go).
This is **Step 0 of 10: conventions + tooling scaffold ONLY — no code moved, behavior-frozen.**
Branched off `main` (`3ff1d9e`); per COLLAB only Nadim merges. The plan was already Codex-reviewed
once (SOUND-WITH-CHANGES) and revised before approval.

### What landed (purely additive + one dead-import removal)
- **`docs/adr/0000-template.md`** + **`docs/adr/0001-modular-monolith.md`** — ADR template + the
  decision record: the layer model, the 6 invariants, the mechanical-enforcement plan, the target
  import-linter contract (as a spec), and alternatives rejected.
- **`CLAUDE.md`** (new) — project guidance: hard rules (Phase 1 frozen, synthetic-only, branch
  model), target architecture + layer rule + invariants + a "where does X go?" table, how to run tests.
- **`COLLAB.md`** — new agent-neutral **"Architecture (layered modular monolith)"** rules section so
  Codex gets the same boundaries as Claude (layers, invariants, adding-work checklist).
- **`pyproject.toml`** (new) — `ruff` config scoped to `app/`+`tests/`+`main.py`; **excludes frozen
  `phase1_cdr/`** + `vendor/` + `.venv` + the JS SPA. `select=["E","F","W"]`, line-length 120 (fits
  the existing code). Import-sorting (`I`) and the ruff/import-linter **CI gates** are deferred to
  **Step 9** (after imports settle) per the plan.
- **`requirements-dev.txt`** (new) — `ruff`, `import-linter` (dev/CI tooling, not runtime).
- **`tests/phase2a/test_bridge.py`** — removed one unused `import os` (the only real ruff finding).

### Verification
- `ruff check app tests main.py` → **All checks passed**.
- `pytest tests/phase2a phase1_cdr/tests` → **117 passed**.
- `git diff --stat -- phase1_cdr/` → **empty** (Phase 1 frozen). No `app/*.py` or `main.py` logic
  changed — the only code edit is the dead-import removal in a test.

### Flags for review
- **import-linter local install:** this dev venv is **win_arm64**; import-linter's `grimp` dep has no
  win_arm64 wheel and tries a Rust source build (fails locally). CI runs on **ubuntu x64** (wheels
  exist), so the Step 9 import-linter CI gate is unaffected — flagging the ARM64-local limitation.
- **Dependency pinning NOT done yet** (a Step 0 sub-item): the plan's constraints/lock must be verified
  in **both** CI jobs (3.11 + 3.12), which only CI can confirm — proposed as a focused follow-up with
  Khaled/CI before Step 9, rather than a possibly-wrong local hand-pin.

### Codex review round 1 — addressed (commit on same branch)
Codex returned **SOUND-WITH-CHANGES** (no behavior change; confirmed 117 passed, `phase1_cdr/`
empty). All four findings were doc/config refinements (the import-linter contract is still only a
*spec* until Step 9) — applied:
- **[Med] auth independence** — added `app.auth` to the ADR independence set (auth is a domain too,
  so invariant 4 covers it).
- **[Med] `flask` is external** — the repo-forbidden import-linter contract now covers only the
  *internal* `app.audit`/`app.api`; the no-`flask`-in-repos rule is explicitly delegated to the AST
  architecture test (avoids needing `include_external_packages` on that contract).
- **[Low] Phase-1 indirect rule** — made explicit as `allow_indirect_imports = true` in the spec.
- **[Low] ruff `force-exclude = true`** — added to `pyproject.toml` so frozen `phase1_cdr/` is
  skipped even on `ruff check .` / explicit paths. Verified: `ruff check .` → all checks passed.

### Codex review round 2 — CLEARED
Codex re-reviewed the fixes (commit `e4a14a5`) and returned **CLEAR FOR MERGE** — all four round-1
findings resolved, no new issues, no behavior change confirmed (117 passed, `phase1_cdr/` empty).

### What's left
- **Nadim ff-merge** of `claude/modular-reorg-step0` into `main` (clean fast-forward — `main` is an
  ancestor); then delete the merged branch and **prune the now-redundant `passwords` branch** (it is
  identical to `main` after the password-meter merge).
- Then **Step 1** — the `app/infra/` package: move `config`/`crypto`/`storage` into `app/infra/`, add
  the single `app/infra/phase1.py` seam (delete the duplicated `sys.path` blocks in `validation.py`
  and `detection_bridge.py`), update the import choreography + affected tests; verify 117 + frozen
  Phase 1. Full per-step detail: plan file `~/.claude/plans/discussion-only-ancient-whistle.md` and
  session log `session-logs/2026-06-30.md`.

## 2026-06-29 — Claude: password strength meter on `passwords` — FOR REVIEW (do NOT merge)

Nadim asked for a **password strength indicator** on the password-creation flows, scored
on the passwordmeter.com additions/deductions model (the two screenshots he sent). It is
**informational only — it never blocks submit** (a weak password can still be created).
Built on `passwords` off `main` (`3ff1d9e`); **frontend-only, fully additive — Phase 2A
backend + `app/ui.py` + Phase 1 byte-frozen** (`git diff --stat main -- 'app/*.py' main.py
phase1_cdr/` → empty). Built + verified live (PyWebView window), **not merged**.

### What landed (all under `app/web/`)
- **`app/web/js/strength.js`** (NEW, only new module). Two exports:
  - `analyzePassword(pw)` — **pure, no DOM** → `{ score 0–100, band 0–4, label, checks }`.
    Faithful passwordmeter scoring: additions (length `*4`, upper/lower `(len−n)*2`, numbers
    `*4`, symbols `*6`, middle num/sym `*2`, requirements `*2`) minus deductions (letters-/
    numbers-only `−len`, weighted case-insensitive repeats, consecutive upper/lower/number
    `−n*2`, sequential letters/numbers/symbols 3+ `−n*3`). Clamp 0–100. Bands: <20 Very Weak,
    <40 Weak, <60 Fair, <80 Strong, ≥80 Very Strong.
  - `strengthMeter(inputEl)` — DOM widget (built with `el()`/`icon()`): the red→green fill
    bar, live label + `score/100`, and a small **info button** that toggles a **checklist
    popover** of 7 best-practice criteria, each ticking **green when met** (filled check) vs
    **muted outline when not**. Re-runs on every `input`.
- **`components.js`** — added `info`/`check`/`circle` SVG paths to the `ICONS` map (no emoji).
- **`screens/login.js`** — mounts `strengthMeter(p)` **only in setup mode** (`isSetup`); the
  sign-in form is untouched (don't grade an existing password at login). Safe in the children
  array because `el()` skips `null`.
- **`screens/password.js`** — mounts `strengthMeter(nw)` under the New-password field; the
  match check + inline messages are unchanged.
- **`css/app.css`** — one new "password strength meter" section using **existing tokens only**
  (`--bad`/`--warn`/`--good`/`color-mix`); band-stepped red→green fill, `ease-out` transitions,
  popover fade via `@starting-style`; the existing reduced-motion block neutralizes it.

### Scoring fix Nadim caught during live review
The raw passwordmeter score clamps to 100 from length/variety **alone**, so a long password
hit **100/100 "Very Strong" with checklist boxes still unticked** — contradictory. Fixed: the
achievable ceiling is now tied to criteria met — `score = min(score, round(met/7 * 100))`.
So **100 is only reachable when all 7 criteria are met**; each unmet box lowers the ceiling
proportionally (e.g. 6/7 caps at 86). Verified: an all-criteria 16-char mix → 100; the same
minus one class or with a repeat/sequence → 86.

### Verification
- `node --check` clean on `strength.js` + the 3 edited modules.
- Pure-logic sanity (throwaway node script, not committed): `aaaaaa`→0, `abc123`→Weak
  (sequence flagged), long-lowercase→Very Weak, all-criteria mix→100, one-box-missing→86;
  `checks` flags all correct.
- `pytest tests/phase2a phase1_cdr/tests` → **117 passed** (frontend-only; `test_ui.py`
  needles unaffected). Backend-frozen diff empty.
- **Live**: launched `python main.py` on an isolated `APP_DATA_DIR` → setup screen renders the
  meter; all 19 modules incl. `strength.js` served 200, zero console errors (only favicon
  404). Nadim confirmed look/feel and the 100-requires-all-criteria fix.

### Self-review cleanups (post-build, `2bf...`)
Ran the `code-review` skill over the diff — no correctness bugs; fixed the two low-severity
cleanups it surfaced:
- **Listener teardown:** `strengthMeter()`'s Esc / outside-click `document` listeners are now
  **bound only while the popover is open and removed on close** (was: two per instance, never
  torn down). Residual edge: navigating away with the popover *open* leaves them until the next
  document click resolves it — negligible (the SPA has no unmount hook; popover is shut for
  virtually all navigation).
- **`repeatPenalty(pw)` computed once** (was twice — score deduction + `noRepeats`); folded
  into a single `rep` local. Scores byte-identical before/after (verified across the sanity set).

### What's left
- **Codex review** of `origin/passwords` (`git diff main..origin/passwords`), then **Nadim
  merge** (only Nadim merges). Frontend auto-covered by the existing CI `frontend` job
  (`node --check` over `app/web/js/**/*.js`).

## 2026-06-29 — Codex: UI/UX redesign review + keyboard-row fix on `codex/ui-ux-redesign-review-fixes`

Reviewed `origin/claude/ui-ux-redesign` at `d5e4617` (the redesign + Khaled's login
copy fix) against `main` (`039a0ef`). Found one real bug and fixed it; stacked on a
review branch off the redesign tip. **Backend (Phase 2A) + Phase 1 byte-frozen.**

### Finding fixed (`app/web/js/components.js:68`)
- `navigableRows()` made each `tr.clickable` keyboard-operable (Enter/Space → row
  click → navigate). But `keydown` bubbles, so pressing Enter/Space on a **nested
  action button** (e.g. dataset Delete) fired the button's native activation *and*
  bubbled to the row handler → `tr.click()` → navigation. Both fired at once.
- Fix: guard the row handler with `if (e.target !== tr) return;` — row-level
  Enter/Space/Arrow handling now runs only when the row itself has focus; nested
  buttons/links keep their own keyboard behavior. Minimal, exactly scoped (the only
  focusable row descendants are buttons/links; `<td>`s are never keydown targets).

### Verification
- `pytest tests/phase2a/test_ui.py` → 8 passed; `pytest tests/phase2a` → 99 passed.
- `node --check app/web/js/components.js` → clean (Claude re-ran; review-side checks
  were Python-only).
- `git diff --stat 039a0ef -- 'app/*.py' phase1_cdr/` → empty (backend + Phase 1 frozen).
- Branch is a clean linear superset of the redesign: redesign → login copy fix →
  this fix, all off `main`.

### What's left
- **Nadim merge** of `codex/ui-ux-redesign-review-fixes` (carries the whole stack).

## 2026-06-29 — Claude: login error copy fix on `claude/ui-ux-redesign` — FOR REVIEW (do NOT merge)

Khaled tested the redesigned desktop app live and flagged that a failed login
renders the raw backend string **"bad credentials"**, which reads unprofessionally.
Frontend-only copy fix stacked on the existing redesign branch; **backend (Phase 2A)
+ Phase 1 byte-frozen.** (Launch note: on this Windows ARM64 machine the venv is x64,
so `platform.machine()` is `AMD64` → the ARM64 path in `main.py` is correctly a
no-op and the default launch path opens the window fine.)

### What changed (one file, `app/web/js/screens/login.js`)
- The submit handler rendered `err.message` verbatim for any `ApiError`; on a 401
  that message is the internal envelope string "bad credentials". Now a **401**
  renders **"Incorrect username or password."** — polished and non-disclosing (does
  not reveal which field was wrong). Genuine validation messages (e.g. the bcrypt
  72-byte **400**) still pass through unchanged; a non-`ApiError` still falls back to
  "Could not sign in." Mirrors the existing pattern in `password.js` (its 401 →
  "Current password is incorrect.").
- Backend left untouched: "bad credentials" is the API error code at `app/auth.py:57`
  and stays frozen — the user-facing wording belongs in the UI layer.

### Verification
- `node --check app/web/js/screens/login.js` → clean.
- `git diff --stat origin/main -- 'app/*.py' phase1_cdr/` → **empty** (backend +
  Phase 1 frozen).
- `pytest tests/phase2a phase1_cdr/tests` → **117 passed** (test_ui needles unaffected).
- Live: relaunched `python main.py`, entered a wrong password → now shows
  "Incorrect username or password." Khaled confirmed.

### What's left
- **Codex review** of `origin/claude/ui-ux-redesign` (now includes this copy fix on
  top of the redesign), then **Nadim merge**.

## 2026-06-28 — Claude: UI/UX redesign (analyst workstation) on `claude/ui-ux-redesign` — FOR REVIEW (do NOT merge)

Nadim asked for the CDR frontend to be rebuilt to mission-critical/government-analyst
standard (Bloomberg/Palantir/ArcGIS bar). Full enterprise restructure of the `app/web/`
SPA on a new branch off `main` (`811e140`). **Backend (Phase 2A) + Phase 1 byte-frozen.**
Built + verified live; **not merged** — per COLLAB.md Codex reviews, only Nadim merges.

### Design decisions (locked with Nadim — do not re-litigate)
1. **Shell:** left icon+label rail · top breadcrumb/context bar · bottom status bar · full-bleed content.
2. **Scope:** full restructure incl. command palette (Ctrl+K) + keyboard-navigable tables.
3. **Color:** restrained steel-cyan (`--accent #4a9ec4`) on deeper blue-black; green/amber/red used ONLY as state signal, never decoration.
4. **Density:** compact (~28px rows, 12px card padding, 13px body / 12px data, 4px radius).

### What changed (all under `app/web/`)
- **css/app.css** — rewritten design system: new token set + explicit type scale
  (removed the off-scale 11px/18px magic numbers), state tints derived via `color-mix`
  from the state vars (removed all hardcoded `#ff9b94`/`#6fd778`/`#14301a`/rgba hex),
  `:focus-visible` rings everywhere, `prefers-reduced-motion`, and the full shell /
  rail / context / status-bar / command-palette CSS.
- **js/layout.js** — `shell()` rebuilt into rail + context bar + content + status bar;
  now returns `{ page, setCrumb, setActions }` so screens drive the breadcrumb/actions
  instead of rendering their own `<h1>`/`result-head`. Active nav by **route-segment
  exact match** — fixes the old `location.hash.startsWith` bug that falsely highlighted
  on nested routes. Collapsible rail, state persisted in `localStorage`.
- **js/statusbar.js** (NEW) — connection dot, active dataset, live counts (pushed by
  screens via `setStatusCounts`, no polling loop), `HH:MM` clock (single tracked timer).
- **js/command-palette.js** (NEW) — Ctrl/Cmd+K focus-trapped overlay; static nav/action
  commands + one per dataset (lazy-loaded); substring filter, Up/Down + Enter, Esc.
- **js/components.js** — added inline-SVG `icon()` set (Lucide-style, no emoji),
  `navigableRows()` keyboard-table helper (tabindex/role + Enter/Space/Arrow), and
  `role="alert"`/`"status"` on `toast()`/`msg()`. `el()`/`clear()`/`confidencePill`/
  `gateTrace` unchanged (XSS-safe core preserved).
- **js/screens/*.js** (all 7) — ported to the shell (`setCrumb`/`setActions`), compact +
  keyboard-navigable tables, thousands separators on counts; results uses `card-head`
  (kept the `confidencePill` import — test needle).
- **js/main.js / store.js / index.html** — init the palette (kept `startRouter`); add a
  display-only `counts` cache; `<main>` landmark + `color-scheme`/`theme-color` meta.

### Verification (all green)
- **Frozen backend:** `git diff --stat main -- app/__init__.py app/auth.py app/imports.py
  app/targets.py app/analysis.py app/account.py app/crypto.py app/storage.py
  app/validation.py app/detection_bridge.py app/audit.py app/config.py app/ui.py
  phase1_cdr/` → **empty**. Only `app/web/**` changed. `app/ui.py` untouched — its
  `<path:filename>` routes already serve the two new JS files.
- `node --check` on every `app/web/js/**/*.js` (incl. new modules) → clean.
- `pytest tests/phase2a phase1_cdr/tests` → **117 passed** (test_ui needles preserved:
  `--accent`, `startRouter`, `ApiError`, `authenticated`, `confidencePill`).
- **Live click-through** (headless Flask + Chrome MCP, isolated `APP_DATA_DIR`, seeded a
  real **3700 imported / 0 skipped** import via curl into the shared DB): setup →
  dashboard (stat tiles + live status counts) → datasets (compact table, thousands sep)
  → **keyboard row Enter navigates** → targets (status bar active-dataset updates) → add
  target → **analyze → results** (Home=Hamra / Work=Downtown, 3 High pills, gate traces,
  frequent-areas table) → **command palette** (open/filter/arrow-Enter-nav/reopen/Esc +
  dynamic dataset command + input focus-trap) → **reload mid-session stays logged in** →
  change-password (Password active in rail foot) → **rail collapse toggles + persists**.
  **Zero console errors** the whole session. Nested-route active state confirmed fixed.

### What's left
- **Codex review** of `origin/claude/ui-ux-redesign`, then **Nadim merge**. Review prompt
  is in session log 2026-06-28 (Session 3). Phase 2A backend + Phase 1 frozen.

## 2026-06-28 — Claude: ARM64 desktop-launch branch CLOSED OUT — Codex all-green, merged, branch pruned

Session-close housekeeping for the ARM64 fix below. Codex reviewed
`claude/arm64-desktop-launch` and returned **all-green with no changes** (nothing to
fix), so the branch == the merged state. Nadim had already fast-forwarded it into
`main` (**tip `059a74e`**, `main` == `origin/main`). Cleanup done this session:

- **Deleted `claude/arm64-desktop-launch`** local + `origin` (was fully merged,
  `git branch -d` clean, no unmerged commits). `git fetch --prune` synced refs.
- **Remaining branches:** `main` + `claude/ui-ux-redesign` (Nadim's active in-progress
  UI work — **intentionally kept**, currently even with `main` but being changed; do
  NOT delete). Untracked `app/web/css/app.css` edit is Nadim's live UI work in progress.
- Repo state: `main` clean + in sync with origin; untracked `.claude/` + `session-logs/`
  as always (local-only).
- Known-inert leftover unchanged: `.git/worktrees/-review-branch-3` still throws
  "Permission denied" on `fetch --prune` housekeeping (stale lock, documented below
  across several entries) — harmless, commits/branch ops unaffected.

ARM64 desktop launch is DONE + merged; next milestone remains **Phase 3 packaging**
(installed/searchable app + icon + shipping the .NET Desktop Runtime).

## 2026-06-28 — Claude: ARM64 desktop launch FIXED on `claude/arm64-desktop-launch` — FOR REVIEW (do NOT merge)

Closed the open ARM64 PyWebView launch follow-up. The desktop window now opens and
renders the live SPA on this Windows ARM64 machine (Nadim confirmed visually).
**Not merged** — branched off `main` (`811e140`); per COLLAB.md only Nadim merges.
The diagnosis in the prior entry (amd64 `ClrLoader.dll`) was a red herring; the real
chain was four distinct ARM64/CoreCLR gaps, each fixed and **gated so it is a no-op
on x64 Windows and on macOS/Linux** (pywebview uses WebKit there, no .NET at all).

### Root cause chain + fixes (all in `main.py`, additive; backend/Phase 1 frozen)
1. **No .NET runtime installed.** Installed **.NET 8 Desktop Runtime (ARM64)** via
   `winget install Microsoft.DotNet.DesktopRuntime.8.arm64`. pywebview already opts
   into CoreCLR (`edgechromium.py:12`); the netfx amd64 shim is irrelevant once we
   stay on CoreCLR.
2. **CoreCLR defaults to `Microsoft.NETCore.App`, which lacks WinForms.**
   `_ensure_arm64_dotnet_runtime()` writes a runtimeconfig targeting
   **`Microsoft.WindowsDesktop.App`** (version auto-detected from the install) and
   calls `pythonnet.set_runtime(get_coreclr(runtime_config=…))` *before* webview
   imports `clr`. Also pre-`AddReference`s the assemblies pywebview imports lazily
   (Microsoft.Win32.SystemEvents, System.Drawing[.Common], System.Diagnostics.Process)
   since CoreCLR doesn't auto-probe the GAC the way netfx did.
3. **pywebview bundles only the net462 WebView2 interop** (`Microsoft.Web.WebView2.
   WinForms.dll` derives from a Control exposing the removed
   `System.Windows.Forms.ContextMenu` → `TypeLoadException` under CoreCLR). Vendored
   the matching **netcoreapp3.0** build (v1.0.3856.49) into
   **`vendor/webview2/netcoreapp3.0/`** and redirect pywebview's `interop_dll_path`
   to it (`_redirect_webview2_interop_to_netcore()`). Native `WebView2Loader.dll` for
   win-arm64 was already bundled by pywebview; WebView2 runtime v149 already present.
4. **pywebview's `OpenFolderDialog` reflects over removed netfx-internal WinForms
   types** (`FileDialogNative+IFileDialog`/`+FOS`) at *class-definition time*, so the
   whole `winforms` backend import dies even though we never open a native folder
   dialog. `_install_winforms_coreclr_shim()` installs a `sys.meta_path` finder that
   source-patches that one class to null-object the absent types. Kept **in-repo** (no
   site-packages edits) so it's version-controlled and survives venv rebuilds; no-op
   if a future pywebview stops using those internals.

### Verification
- `python main.py` → window opens, full SPA loads (`GET /` + all js/css 200 →
  `/api/status` 200), 18 `msedgewebview2` renderer procs live, no errors post-load.
  Nadim confirmed the window is visible/interactive.
- Full suite green: `pytest tests/phase2a phase1_cdr/tests` → **117 passed** (the
  shim is `main()`-only + ARM64-gated, so tests are unaffected). `test_main.py` passes.
- `git diff --stat main -- app/*.py phase1_cdr/` → empty (backend + Phase 1 frozen);
  only `main.py`, `README.md`, and new `vendor/webview2/` change.

### Maintainability flag for Phase 3 (packaging)
pywebview 6.2.1's WinForms backend needed three separate CoreCLR-compat shims — it
predates clean .NET-Core/ARM64 support, so this path is fragile to pywebview upgrades.
When packaging (Phase 3): the installer must ship/declare the .NET Desktop Runtime,
and it's worth weighing whether to keep this patched WinForms path or move Windows to
a backend that doesn't go through .NET. Not blocking; flagged while fresh.

### What's left
- **Codex review** of this branch, then **Nadim merge**.
- This makes the desktop *shell* work; turning it into an installed/searchable app
  with an icon (Start-menu entry, `.exe`/installer) is the deferred **Phase 3**
  packaging work — unchanged by this.

## 2026-06-28 — Claude: Phase 2B live click-through PASSED + MERGED to `main`

Nadim-authorized merge of `codex/phase2b-frontend-review` (`804cc24`) into `main`
after verifying Codex's fix and running the previously-unrun live click-through.

### Live click-through (the last open verification item) — all green
Booted the **real Flask app + `app/ui.py` blueprint headless** (scratchpad
`serve_headless.py`: `create_app()` + `register_blueprint(ui_bp)` on a fixed port,
isolated `APP_DATA_DIR`, PyWebView swapped out) and drove the actual SPA via
Playwright MCP. Verified end-to-end: first-run setup→201, login, dashboard
(client-derived stats), import `sample.xlsx` (**3700 imported / 0 skipped**),
wrong-password→inline 401 (stays on page). **All three behavioural fixes confirmed
in the live UI:**
- **#1 delete dataset → no duplicate nav** — post-delete DOM has exactly 1 `<nav>`,
  1 `<h1>`, 1 page container (the `shell()` `clear()` fix holds).
- **#2 reload mid-session → stays logged in** — hard reload → `/api/status` 200 →
  stays on dashboard, no login bounce.
- **Codex #804cc24 stale-session change-password** — opened the form, killed the
  session underneath (logout), submitted with the *correct* current password →
  **redirected to `#/login`**, NOT the misleading "current password incorrect".
Only console noise = harmless `favicon.ico` 404. Codex's diff reviewed at source
level: correct, incl. the non-JSON-401 edge case and the switch to shared `reset()`.

### NEW FOLLOW-UP (real, non-blocking for this merge): ARM64 PyWebView launch fails
`python main.py` cannot open the native desktop window on this machine (Win ARM64).
pywebview's winforms backend → pythonnet/clr_loader tries to load an **amd64**
`ClrLoader.dll` (`OSError error 0xc1`, bad image) and finds no .NET root → "Failed
to create a .NET runtime". So the packaged desktop shell needs a deps fix (ARM64
.NET runtime / matching pythonnet, or an alternative webview backend) **before any
release**. Does NOT affect the Phase 2B frontend code — the SPA + Flask layer is
fully functional; it's reachable in any browser at the server URL. Flagged for a
dedicated follow-up; Phase 2A backend + Phase 1 remain byte-frozen.

### Merge
- Verified `main` is a direct ancestor → **fast-forward** `git merge --ff-only`.
- Re-ran full suite green before merge: phase2a 99 + phase1 18 = **117 passed**.
- Pushed `main`; deleted the merged `claude/phase2b-frontend` +
  `codex/phase2b-frontend-review` branches (local + origin) per the usual cleanup.

## 2026-06-27 — Codex: Phase 2B frontend review fix on `codex/phase2b-frontend-review`

Reviewed `origin/claude/phase2b-frontend` at `44b5a30` (Claude's branch has 6
commits now, not just the original 2). I did **not** merge and did **not** push.
Found one 401-policy bug in the requested surface and fixed it locally on this
Codex branch.

### Finding fixed
- **Change-password stale-session 401 was treated as a local wrong-password
  error.** `api.js` exempted all `/api/change-password` 401s from the global
  redirect, but Flask's `@login_required` can return the same 401 status with
  `"login required"` before the route reaches the `"old password incorrect"`
  branch. Result: if the session expired while the change-password screen was
  open, the UI stayed on that screen and showed "Current password is incorrect"
  instead of clearing auth state and returning to login.

### Fix
- `app/web/js/api.js` now parses the error envelope before classifying a 401.
  Login 401 remains local; change-password 401 is local only for the parsed
  wrong-current-password response. A parsed `"login required"` 401 now resets
  client auth/cache state and emits `SESSION_EXPIRED`.
- `app/web/js/router.js` suppresses the transient error page for that expected
  redirect signal.
- `app/web/js/screens/password.js` suppresses the misleading inline
  wrong-password message when the wrapper has already classified the error as
  session-expired.

### Review notes
- XSS pass: no `innerHTML`/`outerHTML`/`insertAdjacentHTML`/`document.write` use;
  backend strings (dataset/file names, areas, skip reasons, phones, errors) render
  as text nodes through `el()`/`msg()`/`toast()`. The only backend value placed in
  an attribute is phone number as an `<option value>`, which is not an executable
  sink and is posted back as form data.
- `targets.js` pass: URL dataset id is coerced with `Number(...)`, active dataset
  name recovers from `/api/datasets` on reload, targets are filtered by numeric
  `dataset_id`, and add-target posts numeric `dataset_id` plus a phone selected
  from `/api/datasets/<id>/phone-numbers`.
- Content-type pass: JSON calls still set `Content-Type: application/json`;
  import still passes `FormData` without manually setting `Content-Type`.
- Backend/Phase 1 frozen check stayed empty for the Phase 2A files and
  `phase1_cdr/`.

### Verification
- `node --check` on all `app/web/js/**/*.js` — passed.
- Targeted Node wrapper script — passed: bad login local, wrong current password
  local, stale change-password redirects/resets, JSON header set, FormData header
  omitted.
- `.venv\Scripts\python.exe -m pytest tests\phase2a` — **99 passed**.
- Live PyWebView render still unrun here (needs a display), same as Claude's note.

## 2026-06-27 — Claude: Phase 2B self-review fixes + CI coverage on `claude/phase2b-frontend` (`bb8890a`)

Follow-up on the BUILT entry below. After building, I ran a high-effort self
code-review of the frontend, fixed the findings, and added CI coverage. Branch is
now at **`bb8890a`** on origin; **CI all green** (3 jobs); still **not merged**.

### Self-review findings fixed (`5add8a1`)
- **#1 (HIGH) duplicate nav+page on in-place refresh.** A screen re-invoking
  itself after a delete/add (datasets, targets) re-ran `shell()`, which appended
  a *second* nav + page (the router only `clear()`s on dispatch, not on a direct
  recursive call). Fix: `shell()` (`app/web/js/layout.js`) now `clear()`s `app`
  first — single source of truth, every render path safe.
- **#2 (MED) live session not restored on reload.** `GET /api/status` reports
  `authenticated:true` after a reload but does NOT return the username; the guard
  keyed off `store.username`, so an in-session reload bounced a logged-in user to
  login. Fix: split auth state — `store.authenticated` drives the guard
  (`router.js`/`store.js`/`login.js`), username is display-only. `api.js` now
  clears auth state on a global 401 *before* redirecting, killing a
  login↔dashboard ping-pong the fix would otherwise expose.
- **#3 (LOW)** results-screen dataset-name join now fetches targets+datasets in
  parallel. **#4 (LOW)** folded two `store.js` imports in `layout.js`.
- **Footgun:** removed the unused `innerHTML` branch from `el()` — all backend
  strings render via `textContent`, so there is no XSS sink.

### CI coverage (`bb8890a`)
- `tests/phase2a/test_ui.py` (8 tests, runs in the existing **phase2a** job, no
  Node): serves `index.html` at `/`, css/js assets incl. the nested `screens/`
  path converter, 404 on missing asset, and registering `ui_bp` doesn't disturb
  the API. Suite **109 → 117 passed**.
- `ci.yml` new lightweight **frontend** job: `node --check` on every JS module
  (vanilla no-build SPA → no test framework by design; this is a syntax guard).
- Verified on GitHub Actions run 28292740247: `test` ✓, `frontend` ✓, `phase2a`
  ✓. (One harmless GitHub-wide deprecation *warning* re: setup-node node20 → not
  a failure, not from our config.)

### What's still left (unchanged from below)
- **Codex review** of `origin/claude/phase2b-frontend` @ `bb8890a` (prompt handed
  to Nadim). Then **Nadim merge** (only Nadim merges).
- **Live PyWebView click-through** (`python main.py`) — the one check not runnable
  headlessly; verify the two behavioural fixes: delete a dataset → no duplicate
  nav; reload mid-session → stays logged in.

## 2026-06-27 — Claude: Phase 2B (frontend) BUILT on `claude/phase2b-frontend` (`12bb029`) — ready for Codex review

Executed the Phase 2B plan (`~/.claude/plans/smooth-plotting-reef.md`). The full
desktop UI is built, additive, and verified. **Not merged** — branched off `main`
(`64054cc`); per COLLAB.md, Codex reviews and only Nadim merges.

### What landed (all additive)
- **`app/ui.py`** — new Flask blueprint: serves `index.html` at `/` + `/css/*`,
  `/js/*` static assets via `send_from_directory`. Imports nothing from Phase 2A.
- **`app/web/`** — vanilla no-build SPA: `index.html`, `css/app.css` (dark
  data-terminal design system), `js/{api,router,store,components,layout,main}.js`
  + `js/screens/{login,dashboard,datasets,import,targets,results,password}.js`.
  Hash router, one fetch wrapper (envelope unwrap + 401 policy), 4-state
  confidence pill + labeled gate-trace renderer (never raw JSON).
- **`main.py`** — MODIFIED only: `app.register_blueprint(ui_bp)` after
  `create_app()`; window title → "La Passion — CDR Analysis"; window points at
  `/` (was `/api/health`). Full Phase 2B summary + all 12 API-mismatches block
  added at the top of the file.

### Verification (all green)
- **Backend frozen:** `git diff --stat main -- app/__init__.py app/auth.py
  app/imports.py app/targets.py app/analysis.py app/account.py app/crypto.py
  app/storage.py app/validation.py app/detection_bridge.py app/audit.py
  app/config.py phase1_cdr/` → **empty**.
- **Existing suite:** `pytest tests/phase2a phase1_cdr/tests` → **109 passed**.
- **Static-serving smoke:** `/`, `/css/app.css`, `/js/**` all 200 with correct
  Content-Type; `/api/health` unchanged.
- **Headless E2E** through the EXACT API calls each screen makes (isolated temp
  `APP_DATA_DIR`): setup → import (.xlsx, 84 imported / 1 skipped w/ reason) →
  phone-numbers picker → create target → dup→409 → analyze (home/work pills,
  freq areas+confidence, contacts) → result reload → change-password (wrong
  old→401 inline, correct→200) → logout → post-logout 401. All assertions pass.
- **JS syntax:** `node --check` clean on all 13 modules.

### Pushed to origin (ready to fetch)
Both `main` and the feature branch are on origin. `origin/main` was 1 commit
behind (only the doc commit `a3ebf83`); synced it first so the review diff is
clean. Review range for Codex:
```bash
git fetch --all
git log --oneline main..origin/claude/phase2b-frontend   # e575eb6, 12bb029
git diff main...origin/claude/phase2b-frontend           # 18 files, +1398/-1
```

### What's left / open
- **Codex review** of `origin/claude/phase2b-frontend` (then Nadim merge). Review
  prompt has been handed to Nadim to paste into Codex; focus areas flagged:
  api.js 401 policy (#7), router auth-guard loops, XSS surface (all backend
  strings must go through `textContent`/`el()`, not the `html` attr), targets.js
  active-dataset recovery + `dataset_id` numeric coercion.
- The one verification step I can't run headlessly: live render in the PyWebView
  window (`python main.py`) — needs a display. Code is wired and the API contract
  is fully validated, but a human should click through once before merge.
- Pre-existing inert `.git/worktrees/-review-branch-3` admin folder still throws a
  "Permission denied" on git housekeeping (lock not released); commits succeed
  regardless. `git worktree prune` once the lock clears.

## 2026-06-27 — Claude: Phase 2B (frontend) PLAN complete — ready to EXECUTE next session

Planned Phase 2B with Nadim: the desktop UI + PyWebView shell on top of the
merged Phase 2A backend. **No code written yet** — this is the agreed plan to
execute next session. Backend was read route-by-route, so the API shapes below
are confirmed, not assumed. **Full plan file (authoritative, more detailed):**
`C:\Users\nadim\.claude\plans\smooth-plotting-reef.md`.

### Decisions locked with Nadim (do NOT re-litigate)
1. **Vanilla, no-build SPA** (hand-written HTML/CSS/JS, hash router), served
   same-origin by Flask. No Node/bundler — repo is Python-only, runs offline in
   PyWebView. (Rejected React/Vite and HTMX/Jinja.)
2. **Add-Target phone = picker** populated from `GET /api/datasets/<id>/phone-numbers`
   (not free text) — backend 404s a phone not in the dataset.
3. **Results include `frequent_contacts` + `frequent_areas_confidence`** (both
   returned by analyze; brief omitted them).

### Confirmed API (session-cookie auth, NOT tokens; envelope `{ok,data}` / `{ok,error:{code,message}}`)
`GET /api/status`→`{account_exists,authenticated}` (first-run + boot signal) ·
`POST /api/setup|login|logout|change-password` · `POST /api/imports` (multipart
`name`+`file`)→`{dataset_id,imported,skipped,skipped_reasons[]}` ·
`GET /api/datasets` · `DELETE /api/datasets/<id>` ·
`GET /api/datasets/<id>/phone-numbers`→`[{phone_number,count}]` ·
`GET /api/targets` (ALL datasets, each has `dataset_id`) ·
`POST /api/targets {name,dataset_id(int),phone_number}` · `DELETE /api/targets/<id>` ·
`POST /api/targets/<id>/analyze?top_n=5` · `GET /api/targets/<id>/result`.
Analysis `DetectionResult.confidence` ∈ **{High,Medium,Low,Insufficient data}**
(4 states); `gates`={N,share,closeness,density}, each High/Medium/Low; plus numeric
`share/closeness/density`, `supporting_records/total_window_records`,
`near_tie`, `alternatives[]`.

### Gaps/mismatches found in the brief (resolved in plan; each gets a `// API-MISMATCH:` comment + entry-point summary line)
- No HTML served today → add **`app/ui.py` blueprint**, register it from the
  **entry point** (`app=create_app(); app.register_blueprint(ui_bp)`) so
  `app/__init__.py` + all Phase 2A code stay byte-untouched.
- No stats endpoint → Dashboard derives from datasets+targets. Targets global →
  filter by `dataset_id` client-side. Analyze payload omits dataset name → join
  client-side. Confidence 4th state "Insufficient data" missing from brief →
  4-state pill. **401 is overloaded**: global "401→login" rule applies to the
  authenticated area but NOT to login/change-password (there 401 = bad creds /
  wrong current pw → inline). Content-Type guard returns **415** on non-JSON state
  changes → fetch wrapper sets JSON header; import uses FormData (no manual
  Content-Type). bcrypt 72-byte limit → inline 400.

### Build surface (all additive)
`app/ui.py` (new blueprint) · `app/web/{index.html,css/app.css,js/...}`
(api wrapper, hash router, store, shared components incl. confidence pill +
gate-trace renderer, 7 screen modules) · `main.py` MODIFIED only to register
`ui_bp`, set title **"La Passion — CDR Analysis"**, and point the window at `/`
(not `/api/health`). Aesthetic: dark data-terminal — near-black layered surfaces,
single cool accent, monospace for all data, dense tabular layout, confidence as a
4-state visual signal, gate trace collapsed `<details>` rendered as labeled rows
(never raw JSON).

### EXACT resume instructions (next session)
1. New session → "Read `C:\Users\nadim\.claude\plans\smooth-plotting-reef.md` and
   execute it." (Plan has the full per-screen wiring + verification.)
2. Build on a `claude/` branch off `main` (`64054cc`); per COLLAB.md Codex
   reviews, **only Nadim merges**. Keep Phase 2A + `phase1_cdr/` byte-frozen.
3. Verify: `git diff --stat main -- app/__init__.py app/*.py phase1_cdr/` stays
   empty for Phase 2A files (only `app/ui.py`, `app/web/`, `main.py` change);
   `pytest tests/phase2a phase1_cdr/tests` → still 109 passed; then end-to-end
   through the window (`python main.py`).

## 2026-06-27 — Claude: session close — `branch-3` reviewed, fixed, MERGED to `main` (`64054cc`)

Wrap-up of today's session. Khaled's overnight `branch-3` (his Claude code-review
pass, 10 backend fixes) is now reviewed by both agents, extended, and **merged to
`main`**. Everything below is on `main`, in sync with origin, clean and green.

### What landed on `main`
- Khaled's 10 Phase 2A backend bug fixes (`ae948b3`).
- Claude follow-ups: `_parse_integer` int64-exact parsing (`6dbbffe`); `create_target`
  type guard closing Codex's malformed-input 500 (`089e90b`).
- 30 regression tests across the two Claude commits (`f8e5c4a` + the fix commits).
- HANDOFF housekeeping: restored the dangling 2026-06-26 post-Context7 summary
  (`5823724`); preserved Codex's clean re-review verdict (`64054cc`).

### Review trail (full cross-agent loop)
Claude reviewed Khaled's diff → added tests → Codex reviewed and found a real
`create_target` 500 (Important) → Claude reproduced + fixed it + tested → Codex
re-reviewed **CLEAR FOR MERGE** at `089e90b` (109 passed, Phase 1 frozen) → Claude
independently re-swept all routes for the same pattern, none found → Nadim-authorized
fast-forward merge.

### Verification (on merged `main`)
- `pytest tests/phase2a phase1_cdr/tests` → **109 passed** (91 phase2a + 18 phase1).
- Phase 1 byte-frozen throughout (`git diff --stat main -- phase1_cdr/` empty).

### State / cleanup
`main` is the only branch at `64054cc`, in sync with origin, working tree clean
(untracked: `.claude/`, `session-logs/`). `branch-3` and
`codex/branch-3-rereview-089e90b` merged/recorded then deleted (local + origin).
Codex's `.review-branch-3` worktree removed (an inert `.git/worktrees/` admin folder
remains pending a lock release — `git worktree prune` will clear it).

### Open follow-up (non-blocking)
Confirm the real CDR generator emits **naive local timestamps** — the import-time
tz-aware-timestamp rejection (`app/validation.py`) is correct only under that
contract; if the generator emits UTC/offset ISO strings it would skip valid rows.
Next milestone: **Phase 2B (frontend UI)**.

## 2026-06-27 - Codex: branch-3 re-review at `089e90b` - CLEAR FOR NADIM MERGE

Re-reviewed `origin/branch-3` at `089e90b` after Claude's follow-up for my
`create_target` malformed-input finding. I did not merge and did not push
`branch-3` or `main`; this verdict is recorded on `codex/branch-3-rereview-089e90b`.

### Verdict
Clear. I found no remaining blocker or new malformed-request 500 in the reviewed
surface. Nadim can merge `branch-3` when ready.

### `create_target` fix
- Confirmed fixed: `app/targets.py:18-33` now validates all JSON body values before
  any SQL bind. `dataset_id` must be a real `int` (`bool` rejected) and
  `phone_number` must be a non-empty `str`; malformed object/list/string/float/bool
  values return 400 instead of reaching the SQL binds at `app/targets.py:36-56`.
- The stricter type contract is acceptable for the current Phase 2A JSON API:
  committed tests and the plan pass the numeric `dataset_id` returned by
  `/api/imports`, and phone numbers are strings. If Phase 2B uses a raw DOM
  `<select>` value, the UI should cast `dataset_id` to a number before POSTing;
  I do not see a committed frontend payload this breaks.

### Same malformed-input lens across the branch
- Auth routes use `json_body()` (`app/__init__.py:13-22`) plus explicit string
  guards before `account`/audit calls (`app/auth.py:29`, `app/auth.py:46`,
  `app/auth.py:79`).
- Imports are multipart rather than JSON; the dataset name comes from Flask form
  strings (`app/imports.py:18`), and Excel row values are normalized/validated
  before `executemany` (`app/validation.py:39-115`).
- Analysis route IDs are Flask `<int:...>` path converters, and `top_n` is a query
  string parsed in a guarded `try` and clamped non-negative (`app/analysis.py:33-35`).
- I did not find any other request-controlled field in auth/imports/targets/analysis
  that can reach a SQL bind, `.strip()`, or arithmetic as an unguarded JSON
  object/list and raise a 500.

### Reconfirmed prior notes
- `account.create_account` reorder still looks safe: it exits immediately when
  `auth.json` exists (`app/account.py:91-93`), and the `cdr.db` cleanup is only on
  init failure before `auth.json` is written (`app/account.py:91-110`). With no
  `auth.json`, that DB has no recoverable wrapped key.
- Tz-aware timestamps remain an open data-contract question, not a blocker I can
  close in code review. The current rejection at `app/validation.py:81-82` is right
  iff the real generator emits naive local timestamps.

### Verification
- `..\.venv\Scripts\python.exe -m pytest tests\phase2a phase1_cdr\tests` -> 109 passed.
- `git diff --stat origin/main..HEAD -- phase1_cdr` -> empty.
- Review worktree clean after tests.


## 2026-06-27 — Claude: fixed Codex's `create_target` 500 finding — FOR CODEX RE-REVIEW (do NOT merge)

Codex reviewed `branch-3` and found one Important issue: `create_target` hardened
`name` + the non-object body, but `dataset_id` (checked only `is None`) and
`phone_number` (checked only falsiness) still let a JSON object/array through to
the SQL bind at `app/targets.py:27`/`:29`, raising `sqlcipher3.InterfaceError` → 500
— the exact malformed-input-500 class this branch exists to close. **Verified Codex's
finding** by reproducing all three 500s against `branch-3` before fixing.

### Fix (`app/targets.py`)
Tightened the guard to validate TYPES before any DB call: `dataset_id` must be a
real `int` (bool rejected explicitly — it's an `int` subclass), `phone_number` a
non-empty `str`. Malformed values now return `BAD_REQUEST` 400; the well-formed
happy path is unchanged. Re-ran the repro: all three inputs now return 400.

### Tests (`tests/phase2a/test_review_fixes_branch3.py`)
- `test_create_target_non_int_dataset_id_is_400` — parametrized over
  `{...}`, `[...]`, `"1"`, `1.0`, `True` (all 400).
- `test_create_target_non_string_phone_number_is_400` — parametrized over
  `{...}`, `[...]`, `1000001`, `""` (all 400).
- `test_create_target_valid_request_still_succeeds` — imports a dataset and creates
  a real target (201), proving the stricter guard didn't break the happy path.

### Verification
- `pytest tests/phase2a phase1_cdr/tests` → **109 passed** (was 99). Phase 1 frozen
  (`git diff --stat main -- phase1_cdr/` empty).

### Note on Codex's tz-aware caveat
Agreed and already standing: the tz-aware-timestamp rejection is correct ONLY if the
real generator emits naive local timestamps. That data-contract confirmation is the
open question carried in the `branch-3` fix entry below — not resolved here.

### For Codex
New tip pushed to `origin/branch-3`. Re-review `git diff main..origin/branch-3`;
the `create_target` finding is addressed. Still unmerged — Nadim merges.

## 2026-06-27 — Claude: `_parse_integer` exact-int fix + `branch-3` ready for Codex — FOR CODEX REVIEW

Followed up on the fuzzy-boundary note from my previous entry by actually fixing
it, then prepared `branch-3` for Codex's independent review. Still **for review,
not merged** — Nadim merges.

### What I changed (`app/validation.py`, one function)
`_parse_integer` parsed every value through `float()` first, which loses precision
past 2**53: `float("9223372036854775807")` (int64 max) rounds **up** to `…808.0`,
so the int64 range guard at `validation.py:87` mis-rejected the true maximum, and
the guard's real cutoff was float-rounded rather than exact. Fixed by parsing
**string** values with `int()` first (exact for any magnitude); fractional /
scientific strings (`"1.5"`, `"42.0"`, `"1e3"`) still raise there and fall through
to the unchanged `float()` path that detects and normalizes them. Non-string inputs
(int, float, NaN, bool) keep their exact prior behavior. The int64 guard cutoff is
now precise.

### Tests (in `tests/phase2a/test_review_fixes_branch3.py`)
- Replaced the "fuzzy boundary" companion test with
  `test_max_int64_duration_accepted_exactly` (int64 max now accepted with its exact
  value) + `test_large_fractional_string_still_falls_through_to_float_path` (a
  non-integer string is still caught as fractional, not silently accepted).
- `test_overlong_duration_skipped` (int64 max + 1 → skipped) still holds — the
  cutoff is now exact rather than approximate.

### Verification
- `pytest tests/phase2a phase1_cdr/tests` → **99 passed**, team ARM64 interpreter.
- `git diff --stat main -- phase1_cdr/` EMPTY (Phase 1 frozen).

### For Codex — please review the whole `branch-3` diff vs `main`
`git fetch && git diff main..origin/branch-3`. The branch is three logical layers,
all unmerged:
1. **Khaled's `ae948b3`** — 10 backend bug fixes (see the entry two below for the
   per-fix list). Most worth a skeptical look: the `account.py` create-ordering
   reorder (does deleting a stale `cdr.db` on init failure ever destroy a
   recoverable DB? — I argue no: only reachable when `auth.json` is absent) and the
   tz-aware-timestamp rejection (confirm the real generator only emits naive local
   times).
2. **`f8e5c4a`** — my 15 regression tests pinning Khaled's fixes red→green.
3. **this commit** — the `_parse_integer` exact-int fix + its tests.
Do NOT merge; Nadim merges once you're satisfied.

## 2026-06-27 — Claude (Nadim's machine): regression tests for Khaled's `branch-3` fixes — FOR REVIEW (do NOT merge)

Nadim asked me to review Khaled's `branch-3` code-review fixes and close the
test-gap Khaled himself flagged ("Regression tests still TODO"). Reviewed the
whole `git diff main..branch-3` — **verdict: the 10 fixes are sound and target
real bugs.** Spot-verified the two Khaled flagged for a skeptical look: (a) the
`account.py` reorder's `db_path().unlink()` is only reachable when `account_exists()`
is False (auth.json absent), so it can only ever delete an orphan DB unopenable
without the wrapped key — safe; (b) tz-aware rejection is the right call pending the
naive-local data-contract confirmation.

### What I added (one new file, no app/Phase-1 code touched)
- `tests/phase2a/test_review_fixes_branch3.py` — **15 regression tests**, each
  pinning one fix red→green (revert the fix → the test fails). Covers fixes
  #1 (init-failure retryable + DB cleanup), #2 (`busy_timeout=5000`), #3 (non-object
  JSON body → 400 across setup/login/change-pw/targets), #4 (non-string
  username/password/name → 400, account untouched), #5 (tz-aware ts rejected, naive
  still accepted), #6 (overlong duration skipped, in-range still accepted),
  #7 (`DATASET_DELETE` audit row written), #9 (bridge drops NaT rows).
- **Not covered** (noted in the file): #8 (Windows upload-handle close) and #10
  (`main.py` socket close) — resource-cleanup paths behind `# pragma: no cover` /
  platform GC with no deterministic, non-flaky assertion.

### One thing worth Khaled's eye (not a bug in his fix)
Fix #6's guard `duration > 9_223_372_036_854_775_807` has a **fuzzy true cutoff**:
`validation._parse_integer` parses via `float()`, and int64-max isn't exactly
representable in float64 — `float("9223372036854775807")` rounds *up* to
`…808.0` and is rejected. So the exact boundary is float-rounded, not the literal
int64 max. Pre-existing `_parse_integer` trait, not introduced by the guard; the
guard still does its job (prevents the `OverflowError` that 500s the whole import).
Flagging in case the boundary should be tightened to a round, float-safe cap.

### Verification
- `pytest tests/phase2a phase1_cdr/tests` → **98 passed** (was 83: +15 new tests),
  on the team ARM64 interpreter (`.venv\Scripts\python.exe`).
- `git diff --stat main -- phase1_cdr/` EMPTY (Phase 1 frozen). No `app/` or
  `main.py` change — tests only.

### For the reviewer (Codex/Nadim)
Stacked on top of Khaled's `ae948b3` on `branch-3`. Still **for review, not merged.**

## 2026-06-27 — Claude: code-review pass + bug fixes on `branch-3` — FOR REVIEW (do NOT merge)

Khaled asked for a fresh code-review of the merged Phase 2A backend and to fix
any bugs. Ran the `code-review` skill (high-recall) over `app/` + `main.py`
(branch base = `main` `3fbf7c0`; `branch-3` had no prior diff). Fixes are in the
working tree on **`branch-3`**; **`main` untouched, Phase 1 byte-frozen**
(`git diff --stat main -- phase1_cdr/` empty). Nadim merges — this is for review.

### Bugs fixed (10 files, 10 issues)
1. **`account.create_account` ordering (data-loss).** Wrote `auth.json` BEFORE
   creating the encrypted DB; if `init_schema` failed (disk error, or a stale
   `cdr.db` the new random key can't open) the account became openable over a
   schema-less DB — permanently unusable, `/setup` then 409s — and the conn
   leaked. Now: build+init the DB first, on failure `close()`+`unlink()` the db
   and re-raise so `auth.json` is never written (setup retryable); close conn.
2. **`storage.connect` no `busy_timeout` (concurrency).** Threaded server + a
   per-request connection each → a second writer instantly hit "database is
   locked" (default 0 ms). Added `PRAGMA busy_timeout = 5000`.
3. **Non-object JSON body → 500.** `request.get_json(silent=True) or {}` kept a
   JSON array/scalar, then `body.get(...)` raised. Added `app.json_body()` (coerces
   non-dict → `{}`); used in auth setup/login/change-password + targets create.
4. **Non-string `username`/`password`/`name` → 500 (and a non-string username
   PERMANENTLY locked out the account via the auth `AttributeError`→`AuthError`
   path).** Added `isinstance(..., str)` guards → clean 400.
5. **tz-aware timestamps admitted then crashed analyze.** `validate_row` accepted
   offset-bearing ISO timestamps; a dataset mixing offsets makes pandas yield an
   object-dtype column and the frozen `detect_home`'s `.dt.hour` raises 500 at
   analyze. Now rejected at import (naive-local contract; skip reason recorded).
6. **`duration_seconds` unbounded → whole import aborts.** Only a `<0` guard
   existed; a value above SQLite's signed-64-bit max made the bulk `executemany`
   raise `OverflowError`, 500-ing the entire import (0 rows stored). Now that one
   row is skipped (`> 9_223_372_036_854_775_807`).
7. **`delete_dataset` wrote no audit row** (every other state-changing endpoint
   does). Added `audit.DATASET_DELETE` + write it before commit (rowcount>0).
8. **Import upload handle never closed** (Windows temp-file leak under repeated
   imports). `finally: upload.close()`.
9. **`detection_bridge.rows_to_frame` didn't drop NaT-timestamp rows** like the
   frozen loader does (divergence; a tampered DB could feed NaT to the detectors).
   Added `df[df["timestamp"].notna()].reset_index(drop=True)` to mirror loader.
10. **`main.py` leaked the listening socket** — `server.shutdown()` doesn't close
    the FD. Added `server.server_close()` after `join()`.

### Deliberately NOT fixed (reviewed, left for decision / known weakness)
- `top_n=0` → empty `frequent_areas/contacts`: intentional and locked by
  `test_negative_top_n_does_not_return_garbage`. Left as-is.
- `read_excel(dtype=str)` stringifying numeric phone cells to `'…0.0'`/sci-notation:
  real, but matches frozen Phase 1's own `loader` behavior and depends on the
  still-open "real CDR `area`/number format" question (EXPERT_BRIEF §2). Needs a
  data-contract decision, not a silent heuristic.
- Global `DB_KEY`/`USERNAME` in `current_app.config` (cross-request race under the
  threaded server) and the chunked-`Content-Length` CSRF-guard gap: architectural
  items in Khaled's "weaknesses to review later" bucket, not drive-by fixes.

### Verification
- `pytest tests/phase2a` → **65 passed**; `pytest phase1_cdr/tests` → **18 passed**
  (83 total), on a fresh local `.venv` (Python 3.11→3.12, flask 3.1.3, pandas 3.0.3;
  the team interpreter is Nadim-machine-only, so I rebuilt deps from
  `requirements.txt`). `git diff --stat main -- phase1_cdr/` EMPTY.
- NOTE: the existing suite did not *prove* these fixes — no tests exercise the bad
  inputs (non-dict body, tz timestamp, oversized duration, account-init failure,
  busy_timeout, dataset-delete audit). **Regression tests still TODO** — offered to
  Khaled; not yet written. A reviewer should treat these fixes as test-gap-covered
  by reasoning, not by a red→green test.

### For the reviewer (Codex/Nadim)
Whole-branch diff: `git diff main..branch-3` (one fix commit + this HANDOFF entry).
Two worth a skeptical look: (a) **account.py reorder** — does deleting a stale
`cdr.db` on init failure ever destroy a legitimate prior DB? (only reachable when
`auth.json` is absent, i.e. no recoverable account); (b) **tz-aware rejection** —
confirm the real data generator will only ever emit naive local timestamps, or
this turns valid rows into skips.

## 2026-06-26 — Codex/Claude: post-Context7 review fixes reviewed and merged to `main`

Completed the full post-Context7 review-fix cycle for the Phase 2A backend. Claude
reviewed the codebase against the currently installed library versions, implemented
the fixes on `claude/review-fixes`, and Codex independently reviewed the complete
diff. Nadim merged the reviewed branch into `main`.

### What changed
- Added bcrypt 5.0 password-length validation for the 72-byte limit, returning 400
  instead of 500.
- Replaced delayed in-memory failed-login buffering with immediate append-only
  `login_failures.log` writes.
- Clamped negative `top_n` values.
- Required ISO-8601 timestamp parsing.
- Added upload size limits and JSON 413 responses.
- Added `fsync()` before replacing `auth.json`.
- Fixed startup polling backoff.

### Verification
- Phase 2A suite: **65 passed**.
- Phase 1 suite: **18 passed**.
- Confirmed Phase 1 remained byte-for-byte unchanged.

### Final state
- Codex found no blocking issues.
- Added a documentation note that `login_failures.log` is plaintext and not
  tamper-evident.
- `claude/review-fixes` merged into `main`.
- Repository returned to a clean state.

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
