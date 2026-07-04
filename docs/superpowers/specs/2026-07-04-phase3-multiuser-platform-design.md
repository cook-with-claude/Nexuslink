# Phase 3 — Multi-User LAN Platform: Design Spec

**Date:** 2026-07-04
**Status:** Approved design (pre-implementation)
**Author:** Claude Code (branch `claude/phase3-design`)
**Supersedes framing in:** ADR 0001 §Context (Phase 3 = "multi-user platform with admin
roles, connected over LAN"); `docs/phase3-surface.md` (de-globalization inventory)

## 0. Hard constraints (override everything below)

- **All data is synthetic.** This remains a CS-portfolio project. A LAN multi-user
  server is built here as an *architecture demonstration over synthetic CDRs* — an
  exercise in accountability, access control, and oversight — **not** an operational or
  surveillance system. Any decision that only makes sense against real telecom data or
  real individuals is out of scope and must be flagged, not built.
- **Phase 1 is frozen.** No file under `phase1_cdr/` is edited. `git diff --stat main --
  phase1_cdr/` must be empty at every commit.
- **Behavior-preserving where possible.** The reorg runway (ADR 0001) exists so Phase 3 is
  a *seam swap*, not a rewrite. Reuse the existing seams (`api.guards`, `infra.migrations`,
  `audit.log`, the domain `repo`/`routes` split). Do not erode the CI-enforced boundaries.
- **Never edit a released migration.** Migration 1 is the frozen Phase 2A baseline. All
  schema change is *appended* to `MIGRATIONS` (migration 2, 3, …).
- **Two-agent workflow.** Each increment is an independently reviewable branch; only Nadim
  merges. Ship increments in order; keep the suite green between each.

## 1. Scope

Phase 3 turns the single-user localhost desktop app into a **multi-operator server on a
local network**, with role-based access, an admin approval gate for dataset access, and a
comprehensive tamper-evident activity log the admin can review per operator.

### Resolved decisions (from brainstorming, 2026-07-04)

| # | Decision | Choice |
|---|---|---|
| 1 | Deployment shape | **Real LAN multi-user server** (one Flask host; synthetic/portfolio framing) |
| 2 | DB key / trust model | **Server holds the master key** in memory; unlocked at server start by an admin bootstrap passphrase |
| 3 | Account storage | **`users` table inside the encrypted DB** (replaces per-user `auth.json` sidecars) |
| 4 | Client type | **Browser clients → LAN server.** Desktop PyWebView shell survives as a single-user localhost convenience; not the multi-user path |
| 5 | Roles | **Two: `admin`, `analyst`.** No permission "engine" |
| 6 | Dataset ownership | **Admin imports + owns datasets;** analysts request access |
| 7 | Approval gate | **Dataset-access only.** No per-query approval |
| 8 | Activity logging | **Every operator query/intent is logged** (actor, action, dataset, subject, query params, result summary), admin-reviewable per operator |
| 9 | Loggable reads | Any action that must be logged is an **explicit POST intent** (never a loggable GET — avoids HEAD/prefetch phantom rows, the export-endpoint lesson) |
| 10 | Records browsing granularity | **One "opened dataset" event**, not one row per pagination page |
| 11 | Tamper-evidence | **Hash-chained audit log, built** — with an honest threat model stated (see §7) |
| 12 | Transport | **HTTPS with minimum TLS 1.3**, consuming **internal-CA-issued** certs from secure paths, renewal support, **reverse-proxy-compatible** (`X-Forwarded-*`). CA issuance + device-trust = documented operating model, not app code (§8) |
| 13 | Login rate-limiting | **In scope** — login is network-reachable for the first time (the condition ADR 0001 named) |
| 14 | MFA | **TOTP built** (own late/optional increment) as the working second factor; **client-certificate mTLS documented** as the PKI-aligned alternative (§8.6) |
| 15 | Master-key secret storage | **Manual admin bootstrap passphrase** at server start (never stored unwrapped — strongest form). OS-keyring / TPM / Vault noted as a production seam (§8.5) |
| 16 | Internal-service mTLS | **Not applicable** — this is a modular monolith with no internal service hop (one process, in-process DB). Design-only *if* ever decomposed (§8.6) |

### Security posture map (triage of the enterprise checklist)

Each requirement is classified so the spec neither over-builds security theater nor
silently drops a real need. **Built** = app code this phase; **Covered** = already exists;
**Operating-model** = deployment/org infra, documented not coded; **N/A** = inapplicable to
this architecture.

| Requirement | Class | Where |
|---|---|---|
| TLS 1.3, internal-PKI certs | Built | §8 |
| RBAC + least-privilege (deny-by-default) | Built | §5 |
| MFA (TOTP) | Built (late/optional increment) | §8.6 |
| Encryption at rest (SQLCipher) | Covered (Phase 2A) | — |
| Immutable audit of privileged actions | Built | §7 |
| Login rate-limiting | Built | §4.3 |
| Secrets not in code / secure key handling | Built + Operating-model | §8.5 |
| Reverse proxy + firewall + network segmentation | Operating-model (app is proxy-compatible) | §8, §8.5 |
| Continuous monitoring / patch cadence | Operating-model (+ Dependabot, operational logging) | §8.5 |
| mTLS between internal services | N/A (monolith — no service hop) | §8.6 |
| Client-cert mutual TLS (client↔server) | Operating-model / design-only alt to TOTP | §8.6 |

## 2. Increment plan (Approach A — foundation-first reviewable slices)

Each increment is one branch, green suite, its own ADR where noted. Audit is **not** a late
phase: every increment writes its own audit rows as it is built; §7 only adds the *new*
capture surface (read intents) and tamper-evidence.

Deliberately fine-grained — Nadim's preference is small, individually reviewable steps.
The two largest pieces (3.2, 3.5) are pre-split.

- **3.1 — Migrate-on-login wiring** (ADR 0002). Wire `migrations.migrate(g.db)` into
  `api/guards.py:get_db()` right after `storage.connect`. Tiny, mechanical, independent;
  ships first because every later increment appends a migration.
- **3.2a — De-globalization seam** (ADR 0003, part 1). Introduce `app/auth/session.py`
  per-session identity context and swap the 5 `phase3-surface.md` functions to read it —
  **still single-account, behavior-frozen.** Pure refactor; existing tests stay green
  unchanged. This is the low-risk half.
- **3.2b — Server key model + multi-account** (ADR 0003, part 2). Master-key bootstrap
  unlock; `users` table (migration 2); login = bcrypt against it → session carries
  `user_id` + `role`; first-run admin creation. Behavior *changes* here (multi-account),
  so it is isolated from the refactor above.
- **3.2c — Network + transport baseline.** Persistent `SECRET_KEY` keyfile, bind config,
  login rate-limiting, **HTTPS with min TLS 1.3** + cert loading (§8). The server must bind
  HTTPS to be network-reachable, so this rides with the server-startup work; cert-reload is
  finalized before the UI increment.
- **3.3 — RBAC guards.** `role_required("admin")` beside `login_required`; enumerate the
  admin-only actions; the shared **access-check** guard used by dataset + analysis routes.
- **3.4 — Owner dimension + dataset-access approval** (ADR 0004). Owner/visibility on
  `datasets`; the `requested → approved | denied` state machine; server-enforced access
  with no `requested → executed` path.
- **3.5a — Activity capture.** Read *intents* (frequency, export) become POST + logged; full
  event vocabulary with real operator identity + structured detail; `DATASET_OPENED`. No
  chain yet — pure "every action writes a row."
- **3.5b — Tamper-evidence.** Hash chain (`prev_hash`/`entry_hash`) + append-only triggers +
  chain-verification, layered onto the rows 3.5a already produces.
- **3.6 — UI** (last). Approval queue, activity/audit viewer (filter by operator), user
  management, analyst request-status flow. May itself split per screen if the diff is large.
- **3.7 — MFA (TOTP)** — *late, optional, non-blocking.* Enrollment (QR + secret), code at
  login, recovery codes. Does not gate the core auth→RBAC→approval→audit value (§8.6).

## 3. Data model (appended migrations; migration 1 untouched)

Migration 2 (and possibly 3 if split for reviewability) introduces:

```sql
-- Operators. Soft-disable, never delete: removing an operator would orphan their
-- audit trail, which defeats the point of the trail.
CREATE TABLE users (
  id          INTEGER PRIMARY KEY,
  username    TEXT NOT NULL UNIQUE,
  bcrypt_hash TEXT NOT NULL,
  role        TEXT NOT NULL CHECK (role IN ('admin','analyst')),
  created_at  TEXT NOT NULL,
  disabled    INTEGER NOT NULL DEFAULT 0
);

-- Ownership dimension. Legacy (pre-Phase-3) datasets have owner_id NULL = system/admin.
ALTER TABLE datasets ADD COLUMN owner_id INTEGER REFERENCES users(id);

-- The approval state machine. One live row per (dataset, operator).
CREATE TABLE dataset_access (
  id           INTEGER PRIMARY KEY,
  dataset_id   INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
  user_id      INTEGER NOT NULL REFERENCES users(id),
  status       TEXT NOT NULL CHECK (status IN ('requested','approved','denied')),
  requested_at TEXT NOT NULL,
  decided_at   TEXT,
  decided_by   INTEGER REFERENCES users(id),
  UNIQUE (dataset_id, user_id)
);

-- audit_log gains actor identity, context, structured detail, and the hash chain.
ALTER TABLE audit_log ADD COLUMN user_id    INTEGER REFERENCES users(id);
ALTER TABLE audit_log ADD COLUMN dataset_id INTEGER;
ALTER TABLE audit_log ADD COLUMN target_id  INTEGER;   -- the subject looked at
ALTER TABLE audit_log ADD COLUMN prev_hash  TEXT;
ALTER TABLE audit_log ADD COLUMN entry_hash TEXT;
-- (existing: id, ts, username, event_type, detail). detail becomes JSON: query
-- params + result summary. username stays denormalized for immutable readability.
```

**Access rule (single source of truth, enforced server-side):** operator U may touch dataset
D iff `U.role = 'admin'` **OR** `D.owner_id = U.id` **OR** an `approved` `dataset_access(D, U)`
row exists. This predicate lives in one shared guard (§5), consulted by both the dataset and
analysis routes.

## 4. Server key model, auth, and network baseline (ADR 0003)

### 4.1 Two distinct unlocks
- **Server unlock (once, at startup) ≠ operator login (per person).** First run generates
  the master DB key + creates the first admin account, and wraps the master key under an
  **admin bootstrap passphrase** into a server keyfile (outside the encrypted DB, restrictive
  perms, never committed). Every server start unwraps the master key into process memory
  (passphrase via prompt or environment). This is the "server holds the key" mechanism —
  `storage.connect()` uses the in-memory master key; clients never see it.
- **Operator login** = bcrypt verify against `users` → mint a session carrying `user_id` +
  `role`. No password ever unwraps the DB key in this model (that was the single-account
  design); the server already holds it.

### 4.2 De-globalization (the `phase3-surface.md` swap)
Replace the two process-global config slots with a **per-session identity context**
(`app/auth/session.py`). Rewrite only these five: `_unlock`, `logout`, `get_db`,
`current_username`, and add `current_role`; `login_required` gains a role-aware sibling.
`get_db()` derives the connection from the server-held master key (not `config["DB_KEY"]`).
The read-only consumers listed in `phase3-surface.md` should need **zero** edits — if one
does, the accessor seam leaked and the fix belongs at the accessor.

### 4.3 Network security baseline (login is now reachable)
- **Persistent `SECRET_KEY`** in a server keyfile (generated once). Per-launch secret is
  wrong for a shared server — it would log every operator out on restart.
- **Login rate-limiting**: per-username + per-IP throttle (simple in-memory token bucket;
  resets on restart — acceptable at synthetic/portfolio scope; documented).
- **CSRF**: the SPA is served **same-origin** by the same server, so `SameSite=Strict` +
  the existing JSON-content-type guard on state-changing requests still carry it. No
  cross-origin surface is introduced.
- **Failed-login sidecar** (`audit.write_failed_login`) keeps working; failures now also
  carry the attempted username for the admin activity view.

## 5. RBAC (thin — no engine)

- `role_required("admin")` decorator beside `login_required`. **Admin-only actions:** create
  / disable users, approve / deny dataset access, view the activity log, import + own
  datasets. **Analyst actions:** request dataset access, run analysis on granted datasets,
  view own request status.
- The **access-check** predicate (§3) is one shared guard (candidate: `api.guards` or a small
  `app/access/` service) consulted by dataset and analysis routes — so there is no
  server-side path that skips it. Hiding a UI button is never the control; the guard is.
- Denied access = a deliberate, **logged** `403` (`FORBIDDEN`), never a crash or silent
  no-op.

## 6. Dataset-access approval (ADR 0004)

- State machine: `requested → approved | denied`; an admin may re-decide later
  (`denied → approved`). Every transition writes an audit row (`ACCESS_REQUESTED`,
  `ACCESS_GRANTED`, `ACCESS_DENIED`) with actor + dataset.
- **No bypass:** the analysis and dataset-read routes call the access guard *before* doing
  any work; there is no code path from `requested` straight to `executed`. Enforced by tests
  that hit the API directly (not just the UI).
- New domain `app/access/` (`__init__/repo/routes`): the request/decide workflow. The access
  *predicate* is shared (§5); the *workflow* is this domain. Respects invariant 4 (no domain
  reads another's internals) — cross-domain joins happen through repos returning dicts.

## 7. Activity log + tamper-evidence

### 7.1 What is captured
Every meaningful operator action writes a structured row: **actor (`user_id` + `username`),
event_type, dataset_id, target_id (subject), detail (JSON: query params + result summary),
ts**. Event vocabulary:

| Event | Written by | Notable detail |
|---|---|---|
| `LOGIN_SUCCESS` / `LOGIN_FAILED` / `LOGOUT` | auth | attempted username on failure |
| `DATASET_IMPORTED` / `DATASET_OPENED` | datasets | one `OPENED` per session entry, **not per page** |
| `ACCESS_REQUESTED` / `_GRANTED` / `_DENIED` | access | requester / decider |
| `ANALYZE` | analysis | which of home/work/frequent asked; result areas + confidence |
| `FREQUENCY_QUERY` | analysis | rank_by + all filters (area, date range, hour window, call_type) |
| `EXPORT` | analysis | target(s) exported |

### 7.2 Loggable reads become POST intents
The frequency explorer and any "record a look" endpoint change from GET to **POST** (data
returned in the response body), so each logged row corresponds to one real question an
operator asked — no HEAD/prefetch phantom rows. This is the export-endpoint lesson applied
consistently. Plain records pagination stays GET and is **not** logged per page; the single
`DATASET_OPENED` event covers "operator looked at dataset D."

### 7.3 Hash chain (honest threat model)
- Each row stores `prev_hash` and `entry_hash = H(canonical(row fields) ‖ prev_hash)`.
  `SELECT`-time verification walks the chain; a mutated or deleted row breaks every hash
  after it. Genesis: the chain begins at the first row written post-migration (older rows
  carry NULL chain columns); documented, not hidden.
- SQLite `RAISE(ABORT)` triggers block `UPDATE`/`DELETE` on `audit_log` (append-only).
- **Stated plainly in the spec and UI:** this proves *ordering and integrity against naive or
  accidental edits*, and detects a careless insider. It is **not** proof against an adversary
  holding the master key — they can recompute the chain — unless the chain head is anchored
  outside the mutable store (external notarization / signed export). That external anchor is
  **design-only** here. The value delivered is an accountability demonstrator with an
  explicit boundary, not an overclaimed guarantee.

## 8. TLS / PKI (built app vs. operating model)

**Built in the application:**
- Serves over **HTTPS with a minimum protocol of TLS 1.3** (older versions refused); loads
  certificate + private key from **configurable secure paths** (restrictive perms, never
  committed; no self-signed assumption baked into code).
- Supports **certificate reload for renewal** without dropping sessions (re-read cert/key on
  signal or scheduled reload).
- **HTTP is refused / redirected to HTTPS**; **HSTS** header set.
- **Reverse-proxy compatible**: honors `X-Forwarded-Proto`/`-For` so TLS may instead
  terminate at an internal proxy (the common enterprise topology) without the app
  mis-detecting scheme or client IP.
- Private key handling documented; keyfile perms enforced at startup (warn/refuse on
  world-readable).

**Documented operating model (org infrastructure, outside this repo's code):**
- Certificates issued by the **organization's internal CA** (not self-signed).
- **Managed-device trust**: the internal CA root distributed to client devices automatically
  (MDM / GPO), so browsers trust the server without per-client prompts.
- **Rotation cadence** and secure key storage/backup process.

The app is built to *consume* CA-issued certs and support renewal; the CA and device fleet
are the deployment environment it is designed to fit.

### 8.5 Secrets & the surrounding operating model

- **Master DB key:** never stored unwrapped. Wrapped under the **manual admin bootstrap
  passphrase** entered at server start (decision #15) — the strongest posture, since the
  unwrapped key exists only in process memory. Production seam (design-only): back the
  passphrase / keyfiles with an **OS keyring, TPM, or Vault**; the code isolates key loading
  behind `infra/tls.py` + the bootstrap step so this is a swap, not a rewrite.
- **On-disk secrets** (`SECRET_KEY` keyfile, wrapped-master-key keyfile, TLS private key):
  restrictive perms enforced at startup, covered by `.gitignore`, never committed.
- **Deployment topology (operating-model, documented):** app runs **behind a reverse proxy
  and firewall inside a segmented network**; **continuous monitoring / centralized log
  shipping / patch cadence** are ops processes. Dependency updates are already automated
  (Dependabot); operational logging already exists (`infra/logging_config.py`). None of these
  are app code; they are the environment the app is designed to run in.

### 8.6 MFA and mutual TLS

- **MFA — TOTP (built, increment 3.7, late/optional):** per-operator enrollment (QR +
  shared secret), 6-digit RFC-6238 code required at login after password, one-time **recovery
  codes**. Standard library (`pyotp`). Scoped as a non-blocking increment so the core
  auth→RBAC→approval→audit path ships and is reviewable without it.
- **Client-certificate mutual TLS (design-only alternative):** managed-device client certs
  from the internal CA as the second factor. Documented as the PKI-aligned alternative to
  TOTP; the in-app portion is thin (the work is CA/device provisioning = operating-model), so
  it is not built this phase.
- **Internal-service mTLS — N/A.** This is a **modular monolith**: one Flask process with an
  **in-process SQLCipher file**, so there is no internal service-to-service network hop for
  mTLS to protect. Inventing services purely to secure them would be cargo-cult. Recorded as
  design-only *if and only if* the monolith is later decomposed into separate services or the
  database becomes a networked server — at which point mTLS secures those new hops.

## 9. UI (Phase 3.6, last)

- **Admin — approval queue:** pending `dataset_access` requests with approve / deny (and
  re-decide), each action confirmed and logged.
- **Admin — activity/audit viewer:** browse the log filtered by **operator**, dataset, date,
  and action type; this is where "what did operator X ask for, on which subjects, with which
  queries" is answered. Surfaces chain-verification status.
- **Admin — user management:** create / disable operators, assign role.
- **Analyst — request flow:** request dataset access; a **status indicator**
  (pending / approved / denied) per dataset.
- Built with the existing vanilla no-build SPA patterns (rail + screens; `components.js`
  shared renderers). Reuses the established `el()` textContent builder — no `innerHTML`
  sinks.

## 10. Package structure & boundaries

New/changed, following the CLAUDE.md "where does X go" rule and the CI-enforced layers:

```
app/
  auth/
    session.py     NEW — per-session identity context (the de-globalization target, 3.2a)
    account.py     CHANGED — users-table-backed; multi-account; bootstrap admin (3.2b)
    totp.py        NEW — TOTP enrollment/verify + recovery codes (3.7; pyotp)
    routes.py      CHANGED — login mints role-bearing session; rate-limit; MFA step
  users/           NEW domain — admin user management (__init__/repo/routes)
  access/          NEW domain — dataset-access approval workflow (__init__/repo/routes)
  api/guards.py    CHANGED — current_role(), role_required(), shared access-check
  audit/log.py     CHANGED — hash chain, richer rows, new event vocabulary
  analysis/routes.py  CHANGED — frequency + export become logged POST intents
  datasets/*       CHANGED — owner_id; DATASET_OPENED logging
  infra/
    migrations.py  CHANGED — append migration 2+ (users, dataset_access, audit ALTERs)
    tls.py         NEW (infra) — cert/key loading, reload, HTTPS server config
```

- New domains `users`, `access` added to the import-linter **layers** + **independence**
  contracts and the AST architecture scan; each gets a `tests/phase3/<domain>/` dir.
- Invariants hold: routes call repos (no SQL in routes); repos take `conn`, return dicts,
  import `infra` only, never commit; route owns the unit-of-work → `write_audit` → commit.
- `infra/tls.py` is pure INFRA (no Flask/domain imports); added to the Phase-1 forbidden
  source list like the other infra modules.

## 11. Testing

- New `tests/phase3/{auth,users,access,audit,tls,mfa}/`. Reuse Phase 1 synthetic fixtures;
  **no invented data** beyond synthetic operators.
- **MFA (3.7):** enrollment produces a verifiable secret; a valid TOTP code passes and a
  stale/wrong one fails; a recovery code works once then is consumed; MFA is required only
  after it is enrolled (login without MFA still works for the initial admin bootstrap).
- **Access enforcement tests hit the API directly** — an analyst with no approved access gets
  `403` on the dataset and analysis routes even when bypassing the UI. This is the security
  assertion, not a hidden button.
- **Multi-session isolation:** two concurrent sessions carry distinct identities/roles; one
  operator's context never leaks into another's request.
- **Tamper-evidence:** chain verifies on a clean log; mutating/deleting a row (via a test that
  disables the trigger) fails verification at and after that row; append-only triggers reject
  `UPDATE`/`DELETE`.
- **Migration tests:** fresh DB → migrations 1..N; a Phase-2A-shaped DB adopts cleanly; the
  ALTERs are idempotent under the runner's version gate.
- Architecture tests + `lint-imports` stay enforcing with the two new domains. Phase 1 suite
  unchanged and byte-frozen. Canonical gate = CI (Ubuntu); local = native Windows or WSL.

## 12. Deferred / design-only / risks

- **External audit anchoring** (notarization / signed export of the chain head) — design-only
  (§7.3).
- **Per-query approval** — explicitly out (decision #7); the dataset gate is the meaningful
  control.
- **CA issuance + device-trust automation** — operating model, not app code (§8).
- **Desktop-shell multi-user packaging** — stays deferred; desktop shell remains single-user
  localhost.
- **Risk — bootstrap passphrase UX:** requiring a passphrase at every server start is
  operationally heavier than a localhost app; documented as the cost of "server holds the
  key." Alternative (OS keyring / TPM-sealed master key) noted as a design extension.
- **Risk — `SECRET_KEY` / master-key keyfiles** are new on-disk secrets outside the encrypted
  DB; their perms and non-commit are enforced at startup and covered by `.gitignore`.
- **Increment 3.2 is pre-split** into 3.2a (de-globalization, behavior-frozen), 3.2b
  (multi-account + server key), 3.2c (network + TLS baseline) — per Nadim's small-steps
  preference (§2). 3.5 is likewise split into 3.5a (capture) / 3.5b (chain), and 3.6 may
  split per screen. Each half is an independently reviewable, green-suite branch.
- **MFA (3.7) is deliberately last and non-blocking** — the core value ships without it.
- **New runtime dependency:** `pyotp` (for 3.7 only) — added under `constraints.txt`; if no
  suitable pinned wheel exists for the Python floor, TOTP slips to design-only rather than
  forcing a floor bump (the numpy-bump lesson).
```
