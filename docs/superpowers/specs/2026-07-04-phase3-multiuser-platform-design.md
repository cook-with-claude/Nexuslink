# Phase 3 — Multi-User LAN Platform: Design Spec

**Date:** 2026-07-04
**Status:** Approved design, **revised after Codex review round 1** (branch `claude/phase3-spec-patches`)
**Author:** Claude Code
**Supersedes framing in:** ADR 0001 §Context (Phase 3 = "multi-user platform with admin
roles, connected over LAN"); `docs/phase3-surface.md` (de-globalization inventory — **note the
`DB_KEY` premise is corrected here: under server-holds-key there is no per-session DB key; see §4.2**)
**Review resolutions:** see §13 (maps each Codex finding → how it was resolved)

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
| 10 | Records browsing granularity | **One `DATASET_OPENED` event per (session, dataset), emitted server-side** (deduped in the server, NOT a UI convention) — not one row per pagination page. A direct-API records read still triggers the guard + the once-per-session row (§7.2) |
| 11 | Tamper-evidence | **Hash-chained audit log, built** — with an honest threat model stated (see §7) |
| 12 | Transport | **HTTPS with minimum TLS 1.3**, consuming **internal-CA-issued** certs from secure paths, **reverse-proxy-compatible but only trusting `X-Forwarded-*` from a configured proxy CIDR** (§4.3). Cert *hot-reload* downgraded to a documented restart/reload procedure (§8). CA issuance + device-trust = operating model (§8) |
| 13 | Login rate-limiting | **In scope** — login is network-reachable for the first time (the condition ADR 0001 named) |
| 17 | Live session authority | Cookie carries `user_id` only; **`role` + `disabled` are read from the users row per request** (or via a session epoch) — disabling/re-roling an operator revokes stale sessions (§4.3, §4.4) |
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
- **3.2a — Identity-accessor de-globalization ONLY** (ADR 0003, part 1). Move a **per-session
  identity context** into a SUPPORT module (`app/api/identity.py` — *not* `auth` DOMAIN; see
  §4.2) and swap the **identity** accessors (`current_username`, add `current_role`) to read it.
  **`DB_KEY` is deliberately left process-global here** — see the correction below. Truly
  behavior-frozen for the single account; existing tests stay green unchanged. (Codex #2, #3.)
  > **Why `DB_KEY` is not touched in 3.2a:** in today's single-account model the raw SQLCipher
  > key is *derived from the user's password* at login. It cannot move into the signed (not
  > encrypted) session cookie, and a per-session server-side key cache would be new
  > infrastructure — not a mechanical refactor. So the DB-key half waits for 3.2b, where the
  > server-holds-key model **eliminates per-session keys entirely** (one server master key).
- **3.2b — Server key model + multi-account** (ADR 0003, part 2). Master-key bootstrap
  unlock (fail-closed, §4.1); `users` table (migration 2); login = bcrypt against it → session
  carries **`user_id` only**; first-run admin creation bound to localhost. `get_db()` now uses
  the **process-held server master key** (set once at bootstrap, legitimately process-wide —
  it is the *server's* key, never a user's per-session key). Behavior *changes* here.
- **3.2c — Network + transport baseline.** Persistent `SECRET_KEY` keyfile, bind config,
  login rate-limiting, **trusted-proxy CIDR** for `X-Forwarded-*`, `SESSION_COOKIE_SECURE`,
  **HTTPS with min TLS 1.3** + cert loading (§8). The server must bind HTTPS to be
  network-reachable, so this rides with the server-startup work.
- **3.3 — RBAC guards (role only).** `role_required("admin")` beside `login_required`;
  enumerate the admin-only actions; **per-request role/disabled freshness** (§4.4). The
  **dataset-access predicate is NOT here** — it depends on 3.4's schema, so shipping a stub
  guard now would be a fake that changes meaning later (Codex #11).
- **3.4 — Owner dimension + dataset-access approval + the access predicate** (ADR 0004).
  Owner/visibility on `datasets`; the `requested → approved | denied` state machine; the
  **shared access predicate in a neutral SUPPORT policy module** (§5, Codex #4); server-enforced
  access across **all** subject-data reads (§3, §6, Codex #5) with no `requested → executed` path.
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
row exists. This predicate lives in one shared SUPPORT policy module (§5).

**Enforcement is dataset-scoped but reaches every subject-data path (Codex #5).** Targets,
analysis results, exports, and phone-number pickers are all reachable by `target_id`/`dataset_id`
and each **resolves to its owning dataset and re-checks the predicate** — not just the raw
`/records` route. Concretely, access filtering/gating covers: dataset list, `/records`,
phone-number pickers, target list/create/delete, `target_id → dataset_id` resolution, latest-result
reads, frequency queries, and exports. A `target_id` an operator has no dataset access to must
return `403` (not leak the phone number, name, or a stored result). Lists are **filtered** to the
operator's accessible datasets; single-item reads are **gated**. `403` on a resource whose
existence is itself sensitive is indistinguishable from `404` to a non-owner (no existence oracle).

## 4. Server key model, auth, and network baseline (ADR 0003)

### 4.1 Two distinct unlocks — and the fail-closed locked state (Codex #1)
- **Server unlock (once, at startup) ≠ operator login (per person).** First run generates
  the master DB key + creates the first admin account, and wraps the master key under an
  **admin bootstrap passphrase** into a server keyfile (outside the encrypted DB, restrictive
  perms, never committed). Every server start unwraps the master key into process memory
  (passphrase via console prompt or environment). `storage.connect()` uses the in-memory
  master key; clients never see it.
- **Operator login** = bcrypt verify against `users` → mint a session carrying **`user_id`
  only** (role/disabled are read live, §4.4). No password ever unwraps the DB key in this
  model; the server already holds it.
- **Fail-closed locked state (required).** Because `users`, bcrypt hashes, roles, and
  `disabled` flags live *inside* the encrypted DB, none of them are readable until the master
  key is unwrapped. Therefore:
  - Until bootstrap unlock succeeds, the server serves **only** a `503`/locked status on every
    route (no login, no data). It does not silently behave like a fresh install.
  - `/api/status` must distinguish **`locked`** (DB not unwrapped) from **`uninitialized`**
    (no admin exists) from **`ready`**. It must **never** report "locked" as "no admin exists"
    — that would invite a first-admin takeover.
  - **First-admin creation is a local/console/bootstrap operation, bound to localhost** (or
    gated by the bootstrap passphrase) — **never a public LAN race on `/api/setup`.** Once an
    admin exists, `/api/setup` is closed exactly as today.

### 4.2 De-globalization, corrected (Codex #2, #3)
`phase3-surface.md` framed Phase 3 as de-globalizing **both** `config["USERNAME"]` **and**
`config["DB_KEY"]` into per-session context. That is **half wrong for this trust model**, and
the spec corrects it:

- **`USERNAME`/identity → per-session (correct).** The identity accessor reads a per-session
  context. It carries `user_id`; `current_username()`/`current_role()` resolve from the users
  row (§4.4). This is the genuinely mechanical, behavior-frozen part (increment 3.2a).
- **`DB_KEY` → stays process-global, and that is now CORRECT, not a leak.** Under
  server-holds-the-key there is **one master key for the whole server**, set at bootstrap, used
  by every request's `get_db()`. There is **no per-session DB key** to de-globalize. Trying to
  make it per-session in the single-account model would require caching a password-derived key
  server-side (new infra) or putting it in a signed-not-encrypted cookie (unsafe). So `DB_KEY`
  is simply *reinterpreted* from "the logged-in user's key" to "the server's master key."
- **Layer placement (Codex #3):** the per-session identity context is a **SUPPORT** concern
  (`app/api/identity.py`), **not** `auth` DOMAIN. `api.guards` (SUPPORT) reads it; if the
  context lived in `auth` DOMAIN, `guards → auth` would invert the layer rule. `auth/routes.py`
  (APPLICATION) *writes* it at login/logout — allowed (higher may call lower).
- **Zero-edit consumers:** the read-only `current_username()` call sites in `phase3-surface.md`
  still need **zero** edits — if one does, the accessor seam leaked; fix it at the accessor.

### 4.3 Network security baseline (login is now reachable)
- **Persistent `SECRET_KEY`** in a server keyfile (generated once). Per-launch secret is
  wrong for a shared server — it would log every operator out on restart. (This is *why* stale
  sessions can outlive a restart, which is exactly what §4.4 handles.)
- **`SESSION_COOKIE_SECURE = True`** whenever serving network HTTPS (cookies never sent over
  plaintext) — added alongside the existing `HTTPONLY` + `SameSite=Strict`.
- **Login rate-limiting**: per-username + per-IP throttle (in-memory token bucket; resets on
  restart — acceptable at synthetic/portfolio scope; documented). **Depends on a trustworthy
  client IP**, hence the proxy rule below.
- **Trusted-proxy rule (Codex #10):** `X-Forwarded-Proto`/`-For` are honored **only when the
  request arrives from a configured proxy address/CIDR**; from any other source they are
  ignored. Otherwise a LAN client could spoof `https` scheme (defeating HTTPS detection) or a
  fake source IP (defeating rate-limiting). Direct-bind (no proxy) mode ignores them entirely.
- **CSRF**: the SPA is served **same-origin**, so `SameSite=Strict` + the JSON-content-type
  guard on state-changing requests still carry it. No cross-origin surface is introduced.
- **Failed-login audit, corrected (Codex #7):** once the server is bootstrap-unlocked the
  encrypted DB *is* available before operator login, so a normal operator **`LOGIN_FAILED`
  goes into the encrypted, hash-chained audit log** (with attempted username) — not the
  plaintext sidecar. The `write_failed_login` **sidecar is reserved for pre-unlock / bootstrap
  failures only** (when the DB genuinely cannot be opened). This removes the "sidecar keeps
  working" vs "vocabulary includes `LOGIN_FAILED`" contradiction in the earlier draft.

### 4.4 Live session authority — no stale roles (Codex #8)
Persistent `SECRET_KEY` means sessions survive restarts, so authority **must not be trusted
from the cookie**:
- The cookie carries **`user_id` only**. On **every** request, `login_required`/`role_required`
  load the current users row and read **`role` + `disabled` live**. A disabled or re-roled
  operator loses/loses-elevation immediately, even on a pre-existing cookie.
- Equivalent acceptable implementation: a **session epoch/version** bumped on disable/role-change
  and compared per request. Either way the authoritative source is the DB row, never the cookie.
- This is cheap: every request already opens `get_db()`; the user-row read joins that unit of
  work. Covered by tests (§11): disable-mid-session and role-downgrade-mid-session both revoke.

## 5. RBAC (thin — no engine)

- `role_required("admin")` decorator beside `login_required`. **Admin-only actions:** create
  / disable users, approve / deny dataset access, view the activity log, import + own
  datasets. **Analyst actions:** request dataset access, run analysis on granted datasets,
  view own request status.
- The **access-check** predicate (§3) lives in a **neutral SUPPORT policy module** — **not** in
  the `app/access` workflow domain (Codex #4). Reason: the import-linter independence contract
  names whole domain packages, so `app.datasets.routes → app.access.*` (and `analysis`,
  `targets`) would violate independence. Placement: a small `app/api/policy.py` (SUPPORT) holds
  the predicate; `api.guards` exposes a thin `require_dataset_access(...)` that delegates to it;
  domain routes call the guard. No domain imports another domain's internals; no ad-hoc SQL in
  routes (the predicate's data read goes through a repo).
- Hiding a UI button is never the control; the guard is.
- Denied access = a deliberate, **logged** `403` (`FORBIDDEN`), never a crash or silent no-op.

## 6. Dataset-access approval (ADR 0004)

- State machine: `requested → approved | denied`; an admin may re-decide later
  (`denied → approved`). Every transition writes an audit row (`ACCESS_REQUESTED`,
  `ACCESS_GRANTED`, `ACCESS_DENIED`) with actor + dataset.
- **No bypass:** every subject-data route (§3: records, targets, results, exports, pickers,
  `target_id` resolution — not just dataset+analysis) calls the access guard *before* doing any
  work; there is no code path from `requested` straight to `executed`. Enforced by tests that
  hit the API directly (not just the UI).
- New domain `app/access/` (`__init__/repo/routes`) holds **only the request/decide workflow**
  (the state machine + its audit writes). The access **predicate is NOT here** — it is the
  neutral SUPPORT policy module (§5), precisely so `datasets`/`analysis`/`targets` can consult it
  without importing this domain (independence-contract safe). Cross-domain joins go through repos
  returning dicts.

## 7. Activity log + tamper-evidence

### 7.1 What is captured
Every meaningful operator action writes a structured row: **actor (`user_id` + `username`),
event_type, dataset_id, target_id (subject), detail (JSON: query params + result summary),
ts**. Event vocabulary:

| Event | Written by | Notable detail |
|---|---|---|
| `LOGIN_SUCCESS` / `LOGIN_FAILED` / `LOGOUT` | auth | attempted username on failure; `LOGIN_FAILED` in the encrypted chained log post-unlock, sidecar only pre-unlock (§4.3) |
| `DATASET_IMPORTED` / `DATASET_OPENED` | datasets | `OPENED` emitted **server-side**, deduped once per `(session, dataset)` — not per page, not a UI convention (§7.2) |
| `ACCESS_REQUESTED` / `_GRANTED` / `_DENIED` | access | requester / decider |
| `ANALYZE` | analysis | which of home/work/frequent asked; result areas + confidence |
| `FREQUENCY_QUERY` | analysis | rank_by + all filters (area, date range, hour window, call_type) |
| `EXPORT` | analysis | target(s) exported |

### 7.2 Loggable reads: POST intents + server-enforced `DATASET_OPENED` (Codex #6)
The frequency explorer and any "record a look" endpoint change from GET to **POST** (data
returned in the response body), so each logged row corresponds to one real question an operator
asked — no HEAD/prefetch phantom rows. This is the export-endpoint lesson applied consistently.

**Records browsing** stays a paged GET, but "one `DATASET_OPENED` per look" is **enforced by the
server, not the UI.** The subtlety (Codex #6): a UI-only event would let a direct API caller
`GET /records` and read raw rows with **no** audit row. Resolution: the records route **requires
the access guard and emits `DATASET_OPENED` server-side, deduped once per `(session, dataset)`**
(a per-session marker so pagination doesn't spam the log, but a first raw fetch — from the UI *or*
a direct API client — always produces exactly one row). So there is no way to view a dataset's
records without leaving the promised trail. (This makes the records GET a *committing* read for
its first hit per session; the dedup marker keeps subsequent pages non-writing.)

### 7.3 Hash chain (honest threat model)
- Each row stores `prev_hash` and `entry_hash = H(canonical(row fields) ‖ prev_hash)`.
  `SELECT`-time verification walks the chain; a mutated or deleted row breaks every hash
  after it. Genesis: the chain begins at the first row written post-migration (older rows
  carry NULL chain columns); documented, not hidden.
- SQLite `RAISE(ABORT)` triggers block `UPDATE`/`DELETE` on `audit_log` (append-only).
- **Concurrent append must be serialized (Codex #9).** The desktop server is threaded and each
  request opens its own connection, so two concurrent logged intents could both read the same
  chain head and fork/break the chain. The append (read head → compute `entry_hash` → insert)
  runs under **`BEGIN IMMEDIATE`** (write lock taken before the head read) within the route's
  existing unit-of-work — `busy_timeout` (already 5000 ms) absorbs contention. A single-row
  **`chain_head` table** updated in the same transaction is the alternative; either way the
  head read and the insert are one atomic, serialized step. No two rows share a `prev_hash`.
- **Stated plainly in the spec and UI:** this proves *ordering and integrity against naive or
  accidental edits* and detects a careless insider. It is **not** proof against an adversary
  holding the master key — they can recompute the chain — unless the chain head is anchored
  outside the mutable store (external notarization / signed export = **design-only** here). And
  **tail truncation** (deleting the newest N rows and their head) is undetectable without that
  external anchor. So the UI states **"the stored log verifies"** (internal consistency), **not**
  "the history is complete." An accountability demonstrator with an explicit boundary, not an
  overclaimed guarantee.

## 8. TLS / PKI (built app vs. operating model)

**Built in the application:**
- Serves over **HTTPS with a minimum protocol of TLS 1.3** (older versions refused); loads
  certificate + private key from **configurable secure paths** (restrictive perms, never
  committed; no self-signed assumption baked into code).
- **Certificate renewal via a documented restart/reload procedure** — cert/key are re-read on
  server (re)start. *In-process hot-reload without dropping sessions is **downgraded to a
  documented procedure / later refinement*** (Codex smaller-pushback): it is heavier than this
  portfolio scope needs, and a planned restart on the renewal cadence is sufficient.
- **HTTP is refused / redirected to HTTPS**; **HSTS** header set; `SESSION_COOKIE_SECURE` (§4.3).
- **Reverse-proxy compatible, but trust is gated**: honors `X-Forwarded-Proto`/`-For` **only from
  a configured proxy CIDR** (§4.3, Codex #10) so TLS may terminate at an internal proxy without
  letting arbitrary LAN clients spoof scheme or client IP.
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
  api/
    identity.py    NEW (SUPPORT) — per-session identity context (3.2a; NOT auth DOMAIN, Codex #3)
    policy.py      NEW (SUPPORT) — the neutral dataset-access predicate (3.4; Codex #4)
    guards.py      CHANGED — current_role()/role_required() (live role, §4.4);
                             require_dataset_access() delegating to api.policy
    system.py      CHANGED — /api/status returns locked|uninitialized|ready + user_id/role/MFA (#1,#12)
  auth/
    account.py     CHANGED — users-table-backed; multi-account; bootstrap admin (3.2b)
    totp.py        NEW — TOTP enrollment/verify + recovery codes (3.7; pyotp)
    routes.py      CHANGED — login mints user_id-only session; rate-limit; MFA step;
                             LOGIN_FAILED to encrypted log post-unlock (§4.3)
  users/           NEW domain — admin user management (__init__/repo/routes)
  access/          NEW domain — dataset-access WORKFLOW only (request/decide); NOT the predicate
  audit/log.py     CHANGED — serialized hash-chain append, richer rows, new event vocabulary
  analysis/routes.py  CHANGED — frequency + export become logged POST intents; access-gated
  targets/routes.py   CHANGED — access-gated; target_id -> dataset resolution re-checks (#5)
  datasets/*       CHANGED — owner_id; server-side DATASET_OPENED; list/pickers access-filtered
  infra/
    migrations.py  CHANGED — append migration 2+ (users, dataset_access, audit ALTERs, chain_head?)
    tls.py         NEW (infra) — cert/key loading, HTTPS server config, trusted-proxy config
```

- New domains `users`, `access` added to the import-linter **layers** + **independence**
  contracts and the AST scan; each gets a `tests/phase3/<domain>/` dir. `api.identity` and
  `api.policy` are **SUPPORT** (like `api.guards`) — added to the layers contract there, so
  domains may depend on them without a domain→domain edge.
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
  `403` (indistinguishable from `404`) on **records, targets, results, exports, phone pickers,
  and `target_id` resolution** even when bypassing the UI; list endpoints return only accessible
  datasets/targets (Codex #5). This is the security assertion, not a hidden button.
- **Live session authority (Codex #8):** disabling an operator mid-session revokes on the next
  request; downgrading admin→analyst mid-session loses admin routes immediately — both on a
  pre-existing cookie.
- **Direct-API audit coverage (Codex #6):** a direct `GET /records` (no UI) still produces exactly
  one `DATASET_OPENED` row per session; pagination adds no further rows.
- **Bootstrap locked state (Codex #1):** before unlock every route is `503`/locked; `/api/status`
  reports `locked` (not `uninitialized`); `/api/setup` first-admin creation is refused off-localhost.
- **Trusted-proxy (Codex #10):** spoofed `X-Forwarded-Proto`/`-For` from a non-proxy source is
  ignored (scheme + rate-limit IP unaffected); honored only from the configured CIDR.
- **Multi-session isolation:** two concurrent sessions carry distinct identities/roles; one
  operator's context never leaks into another's request.
- **Tamper-evidence:** chain verifies on a clean log; mutating/deleting a row (via a test that
  disables the trigger) fails verification at and after that row; append-only triggers reject
  `UPDATE`/`DELETE`. **Concurrent-append (Codex #9):** parallel logged intents produce a single
  unbroken chain (no shared `prev_hash`, no fork).
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
- **Increment 3.2 is pre-split** into 3.2a (**identity-accessor de-globalization only** —
  behavior-frozen; `DB_KEY` deliberately untouched, §4.2), 3.2b (multi-account + server key),
  3.2c (network + TLS baseline). 3.5 splits into 3.5a (capture) / 3.5b (chain); 3.6 may split per
  screen. Each half is an independently reviewable, green-suite branch.
- **Cert hot-reload downgraded** to a documented restart/reload procedure (§8) — not built this
  phase (Codex smaller-pushback).
- **Records first-read is a committing GET** (emits `DATASET_OPENED`, §7.2). Accepted trade-off:
  a logged look *is* a state change. The per-session dedup marker keeps later pages non-writing,
  and HEAD/prefetch of `/records` must be handled so it does not emit a phantom open (only a real
  first GET does) — a test pins this.
- **MFA (3.7) is deliberately last and non-blocking** — the core value ships without it.
- **New runtime dependency:** `pyotp` (for 3.7 only) — added under `constraints.txt`; if no
  suitable pinned wheel exists for the Python floor, TOTP slips to design-only rather than
  forcing a floor bump (the numpy-bump lesson).

## 13. Review round 1 (Codex, 2026-07-04) — resolutions

Codex reviewed the original spec on `codex/phase3-design-review` (`92b667d`): *sound direction,
patch before planning 3.2+*. Every finding was verified against the current code model and
accepted; this section maps each to its fix. Findings Codex **agreed with / kept** (trust-model
shape, POST read intents, dataset-level approval, hash-chain honesty, internal-service mTLS N/A)
are unchanged.

| # | Codex finding | Resolution |
|---|---|---|
| 1 | Bootstrap/locked-state fail-closed; `/api/status` must not read locked as "no admin"; first-admin LAN race | §4.1 fail-closed locked state; `503` until unlock; `status` = locked\|uninitialized\|ready; first-admin bound to localhost/bootstrap |
| 2 | 3.2a not a pure refactor — where does the password-derived DB key live? | §4.2 + §2: **`DB_KEY` stays process-global (server master key), not per-session**; 3.2a narrowed to identity accessors only. `phase3-surface.md` premise corrected |
| 3 | `auth/session.py` layer inversion (SUPPORT `guards` → DOMAIN `auth`) | §4.2 + §10: identity context moves to **`app/api/identity.py` (SUPPORT)** |
| 4 | Access predicate in `app/access` violates domain independence | §5, §6, §10: predicate in **neutral `app/api/policy.py` (SUPPORT)**; `app/access` holds only the workflow |
| 5 | Access coverage wider than dataset+analysis | §3, §6, §11: gate/filter records, targets, results, exports, pickers, `target_id` resolution; `403`≡`404` |
| 6 | `DATASET_OPENED` can't be UI-only | §7.2: server-side emit, deduped per `(session, dataset)`; direct-API GET still logs (test) |
| 7 | Failed-login audit contradiction | §4.3: operator `LOGIN_FAILED` → encrypted chained log post-unlock; sidecar only pre-unlock |
| 8 | Stale role/disabled in live sessions | §4.4: cookie carries `user_id` only; role/disabled read live per request (or session epoch); tests |
| 9 | Hash-chain concurrency / tail truncation | §7.3: serialized append (`BEGIN IMMEDIATE`/`chain_head`); UI says "stored log verifies," not "complete" |
| 10 | Blind `X-Forwarded-*` trust | §4.3, §8: honored only from a configured proxy CIDR; `SESSION_COOKIE_SECURE` in HTTPS mode |
| 11 | 3.3/3.4 sequencing (predicate needs schema) | §2: predicate moves to **3.4** (with its schema); 3.3 = `role_required` + admin-action list only |
| 12 | `/api/status` needs Phase 3 semantics | §10: status returns locked\|uninitialized\|ready + `user_id`/`role`/MFA state |
| — | Cert hot-reload heavier than scope | §8, §12: downgraded to a documented restart/reload procedure |
| — | Keep the no-real-telecom-ops boundary loud | §0 unchanged; reaffirmed |
```
