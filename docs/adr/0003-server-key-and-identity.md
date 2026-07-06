# ADR 0003 — Server master key and per-session identity

- **Status:** accepted
- **Date:** 2026-07-05
- **Deciders:** Nadim (merges); proposed by Claude, reviewed by Codex

> **Scope note:** this ADR records the Phase 3 auth/key trust model and is built
> incrementally, appended in place (not minted under a new number — mirroring ADR
> 0002's "Activation" note).
> - **Part 1 (increment 3.2a) — accepted:** identity de-globalization.
> - **Part 2 (increment 3.2b) — server master key + multi-account.** Increment 3.2b
>   was sub-split along the key-model / account-model fault line. **Part 2a
>   (increment 3.2b-1, dated section below) is accepted:** the server holds one
>   master key, unwrapped at a manual bootstrap passphrase, with a fail-closed
>   `503 LOCKED` gate; login/logout decouple from the key; single-account `auth.json`
>   is retained but holds no key material. **Part 2b (increment 3.2b-2) is pending:**
>   the multi-account `users` table replacing `auth.json`, `session["user_id"]`, and
>   the `uninitialized`/`ready` status split — it will extend the same Part 2 record.

## Context

Today auth state is two process-global slots in `app.config`: `DB_KEY` (the raw
SQLCipher key) and `USERNAME` (the logged-in operator), both set at login and
cleared at logout. Phase 3 turns the app into a LAN multi-user server that can
hold **more than one unlocked operator at once** — so identity cannot be a single
process global shared across all connected clients. The de-globalization surface
was inventoried pre-Phase-3 (`docs/phase3-surface.md`) behind a single accessor
seam (`api.guards.current_username()`, ADR 0001 invariant 6) precisely so this
move changes one function body, not every call site.

The design review (spec §4.2, Codex #2/#3) corrected an early premise: under the
chosen **server-holds-the-master-key** model, only *identity* de-globalizes.
`DB_KEY` stays process-global because there is exactly **one** master key for the
whole server; there is no per-session DB key to eliminate.

## Decision

**Part 1 (3.2a): identity is a per-session, data-free SUPPORT context.**

- Add `app/api/identity.py` (SUPPORT). It stores the operator identity — the
  username today, `user_id` in 3.2b — in Flask's **signed `session` cookie**
  (already per-client). It imports `flask` only.
- **Rule:** `app/api/identity.py` is a **leaf** — it must never import an `app.*`
  module, open the database, or issue SQL. A SUPPORT module that read the DB would
  invert the layer rule. DB-backed identity/role accessors
  (`authz.current_username()` / `authz.current_role()`, resolving `role`/`disabled`
  from the `users` row) are an **`authz`-tier** concern and arrive with
  multi-account (3.2b/3.3), not here. Enforced by `tests/architecture/`
  (`test_identity_context_is_data_free`) + the import-linter layers contract.
- `api.guards.current_username()` swaps its body to delegate to
  `identity.current_username()`. Read-only call sites are untouched (invariant 6).
- `auth/routes.py` (APPLICATION) writes the identity at login/setup and clears it
  at logout/failed-auth. `DB_KEY` remains a process-global `app.config` slot and is
  **not** moved to the session.

## Consequences

- **Easier/safer:** identity is now per-client; the server is structurally ready to
  hold several unlocked operators once multi-account lands. The move is
  behavior-frozen for the single-account desktop app (one session).
- **Giving up:** nothing observable today. Identity now rides the session cookie
  (already signed, `HttpOnly`, `SameSite=Strict`), so it is bounded by the cookie's
  integrity — acceptable, and the same store `session["authenticated"]` already uses.
- **Defers to 3.2b (part 2):** the server master key set at a manual bootstrap
  passphrase; the `users` table (bcrypt hashes, roles, `disabled`) replacing
  `auth.json`; `session` carrying `user_id` (not a bare username) with live
  role/`disabled` read per request via `authz`. Trigger: increment 3.2b. Those
  append to this ADR.

## Alternatives considered

- **De-globalize `DB_KEY` into per-session context too** (the original
  `phase3-surface.md` premise) — rejected: under server-holds-the-master-key there
  is one key for the whole server; a per-session key would mean caching a
  password-derived key server-side (new infra) or putting it in a
  signed-not-encrypted cookie (unsafe). `DB_KEY` is reinterpreted as the server key,
  not eliminated. (spec §4.2, Codex #2)
- **Put the identity context in `auth/` DOMAIN** (an early `auth/session.py` idea) —
  rejected: `api.guards` (SUPPORT) reads it, so `guards → auth` would invert the
  layer rule. It belongs in SUPPORT (`app/api/identity.py`). (spec §4.2, Codex #3)
- **Store live role/username in this SUPPORT context** — rejected: those need a DB
  read and must be `authz`-tier; SUPPORT stays data-free. (spec §5, Codex #4)

---

## Part 2 (increment 3.2b-1): the server master key and the fail-closed lock gate

- **Status:** accepted
- **Date:** 2026-07-06
- **Deciders:** Nadim (merges); proposed by Claude, subagent-driven build

### Context (Part 2)

Part 1 left `DB_KEY` as the one remaining process-global — reinterpreted (spec §4.2)
as the *server's* master key rather than a per-session, password-derived key, but
still **set at login** the old way: the single account's password unwrapped the raw
SQLCipher key. That is the last piece tying the encryption key to a user's password,
and it cannot survive multi-account: several operators cannot each derive the *one*
server key from their own password. The key must be owned by the **server process**,
established **before any login**, so login becomes pure authentication.

### Decision (Part 2, 3.2b-1)

**The server holds one master key, unwrapped at startup; login/logout no longer touch it.**

- **Bootstrap keyfile (`app/infra/bootstrap.py`, INFRA leaf).** The server owns a
  random 256-bit master key, generated on first run and stored **wrapped** under a
  bootstrap passphrase in a gitignored keyfile `server.key` in the app data dir
  (`{kdf_salt, nonce, wrapped_key}`, base64; `0600` best-effort, a no-op on Windows).
  The raw key lives only in process memory. `bootstrap.unlock(passphrase)` generates +
  persists the key on first run, else unwraps the existing keyfile; it raises
  `BootstrapError` on an empty/wrong passphrase or a corrupt keyfile. The module
  manages the keyfile and returns bytes — it never opens the DB and imports no Flask.
- **Startup unlock (`main.py`).** `resolve_and_unlock()` reads the passphrase from
  `LP_BOOTSTRAP_PASSPHRASE` (env), else a `getpass` console prompt, and sets
  `app.config["DB_KEY"]` to the unwrapped key — or to `None` if unlock fails. **The
  server never crashes on a bad passphrase; it starts LOCKED.**
- **Fail-closed lock gate (`api.guards.install_lock_gate`).** A `before_request`
  hook returns **`503 LOCKED`** for every `/api/*` route while `DB_KEY is None`,
  **except `/api/health` and `/api/status`** (so a client can observe the locked
  state) and the non-`/api` SPA shell (so a locked server can still serve the page
  that reports it is locked). This is the server-wide unlock gate — distinct from
  `login_required`, which gates a per-session login once the server is unlocked.
- **`/api/status` reports `locked`.** It now returns `{locked, account_exists,
  authenticated}`, where `locked = (DB_KEY is None)`, so the first-run/login UI can
  distinguish a locked server from an un-set-up one.
- **Login/logout are session-only.** `login` authenticates (bcrypt) and establishes
  the session identity (`_unlock` → `identity.set_identity` + `session["authenticated"]`)
  but does **not** derive or set `DB_KEY`. `logout` clears the session but does **not**
  clear `DB_KEY` — the master key is process-wide, so locking it would lock the server
  for every other operator. The fail-closed guarantee therefore moves from "`DB_KEY`
  is `None`" to "**no session identity is granted**": an unauditable login/setup calls
  `_lock()` (session-only) and re-raises to the 500 path.
- **`auth.json` holds no key material.** It records exactly
  `{username, bcrypt_hash, created_at}`. `authenticate()` is a bcrypt-only credential
  check; no key is derived from the password.

### Consequences (Part 2, 3.2b-1)

- **Structurally ready for multi-account:** the key is server-owned and login is pure
  auth, so 3.2b-2 can add a `users` table without touching the key model.
- **Operational change:** the app no longer starts unattended — an operator must
  supply the bootstrap passphrase (env or console) once per process start. Documented
  in the README "Server bootstrap" note. No PyWebView passphrase dialog this
  increment.
- **Behavior change — `create_account` no longer builds the DB.** Previously setup
  derived the key and eagerly built the encrypted `cdr.db` (cleaning a stale one
  first), so setup was retryable. Now the master key is a process concern, so
  `create_account` only writes `auth.json`; **the encrypted DB is built lazily by the
  first `get_db()`** via the migration seam (ADR 0002). Consequence: if the SETUP
  audit's lazy DB build fails, `auth.json` already exists, so `/api/setup` returns
  `409 ACCOUNT_EXISTS` on retry — but the account is **recoverable via `/api/login`**,
  whose own audit write builds the DB. The old "setup builds+cleans the DB and is
  retryable" behavior (and its test) was intentionally removed.
- **Fresh installs only (this increment).** No `auth.json`-with-key → keyfile legacy
  adapter: an existing dev install predates the keyfile, so its `cdr.db` was encrypted
  under a password-derived key the new bootstrap key cannot open. The one-time reset
  (delete the old `cdr.db` + `auth.json`, then relaunch) is documented in the README;
  the data is synthetic, so nothing real is lost.

### Deferred to 3.2b-2 (Part 2b, extends this record)

- The multi-account **`users` table** (a new migration 2 — append to `MIGRATIONS`,
  never edit migration 1) with bcrypt hashes, roles, and `disabled`, **retiring
  `auth.json`**.
- **Multi-account login** verifying bcrypt against the `users` row, and
  `session["user_id"]` (not a bare username) with live role/`disabled` read per
  request via `authz`.
- The **`uninitialized`/`ready`** `/api/status` split (today it reports the binary
  `locked`), plus first-admin-bound-to-localhost setup.

### Alternatives considered (Part 2, 3.2b-1)

- **PyWebView passphrase dialog at startup** — deferred: the desktop shell is a
  single-user localhost convenience; the LAN server is driven from a console, so
  env/console unlock covers both. A GUI prompt can be added later without changing the
  key model.
- **Legacy `auth.json`→keyfile migration** — rejected for synthetic/portfolio data:
  a one-time reset is simpler and lossless here (see Consequences). A real deployment
  would need a re-key/re-import migration; marked design-only.
- **Crash on a bad bootstrap passphrase** — rejected: a LAN server that exits on a
  typo is worse than one that starts LOCKED and serves `503` until restarted with the
  right passphrase (health/status stay observable throughout).
