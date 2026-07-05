# Phase 3 De-globalization Surface Map

> **Purpose:** Phase 3 replaces today's *process-global* auth/unlock state with *per-session* context so
> the app can hold more than one unlocked account at a time. This file is the exact inventory of every
> place that reads or writes that global state, so Phase 3 is a mechanical swap, not a re-discovery.
> Compiled by tracing the code pre-Phase-3; **re-grep before you start** (`DB_KEY|USERNAME|current_username|get_db|session\[|authenticated`) in case anything drifted.

> **✅ STATUS (2026-07-05, after increment 3.2a merged — `0e90bdb`):** the **identity** half of this
> map is **done**. `USERNAME` no longer exists as a process-global — the operator username now lives in
> the signed session cookie via `app/api/identity.py` (SUPPORT), read through `current_username()`
> (ADR 0003 pt 1). `config["USERNAME"]` and its `__init__.py` default were removed. **What remains for
> 3.2b:** `DB_KEY` is *reinterpreted* as the server master key (set at bootstrap, not de-globalized),
> plus the new multi-account `users` table + role/`disabled` resolution. Re-grep confirms no other
> drift. Rows below are annotated **[3.2a DONE]** / **[3.2b TODO]**.

> **⚠️ CORRECTION (2026-07-04, after the Phase 3 design + Codex review round 1):** this map's
> premise that **both** `DB_KEY` **and** `USERNAME` de-globalize to *per-session* context is only
> half right for the chosen trust model. Under **server-holds-the-master-key** (see the design
> spec `docs/superpowers/specs/2026-07-04-phase3-multiuser-platform-design.md` §4.2):
> - **`USERNAME`/identity → per-session** ✅ (moves to a SUPPORT identity context, `app/api/identity.py`).
> - **`DB_KEY` → stays process-global** — it is *reinterpreted* from "the logged-in user's
>   password-derived key" to "the server's one master key, set at bootstrap." There is **no
>   per-session DB key** to eliminate. Do **not** try to move `DB_KEY` into session context.
> The tables below still correctly locate the call sites; only the `DB_KEY` *destination* changes.

## The global state (now 2 live slots — was 3)

| Slot | Lives in | Set by | Read by | Status |
|---|---|---|---|---|
| `current_app.config["DB_KEY"]` | Flask app config (process-global) | `auth/routes.py:_unlock` (login/setup), cleared in `_lock`/`logout` | `api/guards.py:get_db` (opens the SQLCipher conn), `api/guards.py:login_required` (gate) | **[3.2b TODO]** stays process-global; *reinterpreted* as the server master key set at bootstrap |
| `session["username"]` | signed cookie (per-client) | `api/identity.py:set_identity` via `_unlock`, cleared by `clear_identity`/`session.clear()` | `api/guards.py:current_username` → `identity.current_username` | **[3.2a DONE]** was `config["USERNAME"]`; now per-session |
| `session["authenticated"]` | signed cookie (already per-client) | `auth/routes.py:_unlock`, cleared in `_lock`/`logout` | `login_required`, `api/system.py:status` | unchanged |

The identity slot is now per-session (3.2a). **`DB_KEY` is the only remaining `config[...]` global**, and
it does **not** get eliminated — it is repurposed as the server's one master key (3.2b, spec §4.2).

## The seam (identity swap done in 3.2a)

`api/guards.py` was written so Phase 3 changes **one accessor body**, not every call site
(ADR 0001, invariant 6):

- `current_username()` — the single read accessor for identity. Callers never read
  `config["USERNAME"]` directly. **[3.2a DONE]** its body now delegates to the per-session identity
  context (`app/api/identity.py`, SUPPORT — design spec §4.2). The ~7 call sites were untouched, exactly
  as the seam intended. **3.2b** adds `current_role()` alongside it (DB-backed, resolved from the
  `users` row — an `authz`-tier concern, not this data-free SUPPORT module).
- `get_db()` — the single per-request connection factory. **CORRECTED (see banner + spec §4.2):**
  under server-holds-the-master-key, `get_db()` opens the connection from the **process-held
  server master key** set once at bootstrap — *not* a per-session key. `config["DB_KEY"]` is
  **reinterpreted** as "the server's master key," **not** de-globalized. This is still where
  **migrate-on-login** wires in (ADR 0002): `migrations.migrate(g.db)` right after
  `storage.connect(key)`.

## Exact call sites

### Writers (set/clear the globals) — `app/auth/routes.py` **[updated 3.2a]**
- `_unlock(username, db_key)` (L16): sets `config["DB_KEY"]`, calls `identity.set_identity(username)`
  (→ `session["username"]`), sets `session["authenticated"]=True`.
- `_lock()` (L22): sets `config["DB_KEY"]=None`, `session.clear()` (clears `authenticated` + `username`).
- Default declared in `app/__init__.py` (`DB_KEY=None` only; the `USERNAME=None` default was removed).

### The accessors — `app/api/guards.py` **[current]**
- `get_db` (L20) → `config.get("DB_KEY")`, then runs the migration seam before caching `g.db`.
- `current_username` (L41) → delegates to `identity.current_username()` (session-backed).
- `login_required` (L47) → `session.get("authenticated")` **and** `config.get("DB_KEY")`.

### Read-only consumers (call the accessors, **no change needed** — the accessor swap held)
- `current_username()` callers: `auth/routes.py` (L88, L110), `datasets/routes.py` (L66, L144),
  `targets/routes.py` (L62, L81), `analysis/routes.py` (L49, L142).
- `get_db()` callers: every route module + `auth/routes.py:_audit`.
- `session.get("authenticated")` reader: `api/system.py:status` (L22).

## Phase 3 change plan (CORRECTED for server-holds-the-master-key — see spec §4.2)

The original plan assumed `DB_KEY` de-globalizes to per-session context. **It does not** in the chosen
trust model. Progress against the corrected plan:

1. ✅ **[3.2a DONE]** Per-session identity context in **`app/api/identity.py` (SUPPORT)** — today carries
   just `username` in the session cookie; deliberately **data-free** (no DB). (NOT `auth/session.py`;
   SUPPORT `guards` must not import `auth` DOMAIN — spec §4.2, Codex #3.)
2. ✅ **[3.2a DONE]** `current_username()` delegates to it; `_unlock`/`_lock` write/clear it. `get_db` was
   **not** rewritten to be per-session — it keeps using the process-held master key. The ~7 call sites
   were untouched.
3. ✅ **[3.1 DONE]** `migrations.migrate()` wired into `get_db()` (ADR 0002) — still correct.
4. **[3.2b TODO]** `DB_KEY` is **not** removed from config — repurpose it as the server master-key slot,
   set at bootstrap (not at login). Add the multi-account `users` table (new migration; append to
   `MIGRATIONS`, never edit migration 1) + `user_id` in the session context + a DB-backed `current_role()`
   / `disabled` resolution. `login_required` reads live role/disabled from the `users` row (spec §4.4),
   not the cookie. Appends **ADR 0003 part 2**.
5. Everything in "read-only consumers" needed **zero** edits in 3.2a (the seam held); the same should
   hold in 3.2b — if it doesn't, the accessor seam leaked; fix at the accessor, not the call site.

## Schema implication (flagged, not designed here)
Multi-account almost certainly needs an owner/account dimension on the data tables (`datasets`,
`targets`, …). That is a **new migration** (append to `MIGRATIONS`; never edit migration 1) and is the
reason the "typed row models" cleanup was deferred to Phase 3 — the row shapes change here.
