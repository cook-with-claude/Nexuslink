# ADR 0003 — Server master key and per-session identity

- **Status:** accepted
- **Date:** 2026-07-05
- **Deciders:** Nadim (merges); proposed by Claude, reviewed by Codex

> **Scope note:** this ADR records the Phase 3 auth/key trust model and is built
> incrementally. **Part 1 (increment 3.2a, this record) covers identity
> de-globalization.** **Part 2 (increment 3.2b)** — the server master key set at a
> manual bootstrap passphrase and the multi-account `users` table replacing
> `auth.json` — will be appended as a dated section to *this same ADR*, not minted
> under a new number (mirroring ADR 0002's in-place "Activation" note).

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
