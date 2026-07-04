# Phase 3 De-globalization Surface Map

> **Purpose:** Phase 3 replaces today's *process-global* auth/unlock state with *per-session* context so
> the app can hold more than one unlocked account at a time. This file is the exact inventory of every
> place that reads or writes that global state, so Phase 3 is a mechanical swap, not a re-discovery.
> Compiled by tracing the code pre-Phase-3; **re-grep before you start** (`DB_KEY|USERNAME|current_username|get_db|session\[|authenticated`) in case anything drifted.

> **⚠️ CORRECTION (2026-07-04, after the Phase 3 design + Codex review round 1):** this map's
> premise that **both** `DB_KEY` **and** `USERNAME` de-globalize to *per-session* context is only
> half right for the chosen trust model. Under **server-holds-the-master-key** (see the design
> spec `docs/superpowers/specs/2026-07-04-phase3-multiuser-platform-design.md` §4.2):
> - **`USERNAME`/identity → per-session** ✅ (moves to a SUPPORT identity context, `app/api/identity.py`).
> - **`DB_KEY` → stays process-global** — it is *reinterpreted* from "the logged-in user's
>   password-derived key" to "the server's one master key, set at bootstrap." There is **no
>   per-session DB key** to eliminate. Do **not** try to move `DB_KEY` into session context.
> The tables below still correctly locate the call sites; only the `DB_KEY` *destination* changes.

## The global state (3 slots)

| Slot | Lives in | Set by | Read by |
|---|---|---|---|
| `current_app.config["DB_KEY"]` | Flask app config (process-global) | `auth/routes.py:_unlock` (login/setup), cleared in `logout` | `api/guards.py:get_db` (opens the SQLCipher conn), `api/guards.py:login_required` (gate) |
| `current_app.config["USERNAME"]` | Flask app config (process-global) | `auth/routes.py:_unlock`, cleared in `logout` | `api/guards.py:current_username` |
| `session["authenticated"]` | signed cookie (already per-client) | `auth/routes.py:_unlock`, cleared in `logout` | `login_required`, `api/system.py:status` |

The cookie is already per-client; the **two `config[...]` slots are the actual globals** to eliminate.

## The intended seam (already in place)

`api/guards.py` was written so Phase 3 changes **one accessor body**, not every call site
(ADR 0001, invariant 6):

- `current_username()` — the single read accessor for identity. Callers never read
  `config["USERNAME"]` directly. Phase 3 swaps its body to read per-session context.
- `get_db()` — the single per-request connection factory. Phase 3 derives the key from session context
  instead of `config["DB_KEY"]`, and is also where **migrate-on-login** wires in (ADR 0002):
  `migrations.migrate(g.db)` right after `storage.connect(key)`.

## Exact call sites

### Writers (set/clear the globals) — `app/auth/routes.py`
- `_unlock(username, db_key)` (~L15): sets `config["DB_KEY"]`, `config["USERNAME"]`, `session["authenticated"]=True`.
- `logout` (~L71): sets both `config` slots to `None`, `session.clear()`.
- Defaults declared in `app/__init__.py` (`DB_KEY=None`, `USERNAME=None`).

### The accessors — `app/api/guards.py`
- `get_db` (L18) → `config.get("DB_KEY")`.
- `current_username` (L28) → `config["USERNAME"]`.
- `login_required` (L33) → `session.get("authenticated")` **and** `config.get("DB_KEY")`.

### Read-only consumers (call the accessors, **no change needed** if the accessors are swapped correctly)
- `current_username()` callers: `auth/routes.py` (L69, L90), `datasets/routes.py` (L66, L98),
  `targets/routes.py` (L62, L81), `analysis/routes.py` (L49).
- `get_db()` callers: every route module + `auth/routes.py:_audit`.
- `session.get("authenticated")` reader: `api/system.py:status` (L22).

## Phase 3 change plan (implied by the above — not a commitment)

1. Introduce per-session unlock context (candidate: `app/auth/session.py`, referenced in CLAUDE.md).
2. Rewrite **only** `_unlock`, `logout`, `get_db`, `current_username`, `login_required` to use it.
3. Wire `migrations.migrate()` into `get_db()` (ADR 0002).
4. Remove the `DB_KEY`/`USERNAME` config defaults from `create_app()`.
5. Everything in "read-only consumers" should need **zero** edits — if it doesn't, the accessor seam
   leaked and that's a design signal to fix at the accessor, not the call site.

## Schema implication (flagged, not designed here)
Multi-account almost certainly needs an owner/account dimension on the data tables (`datasets`,
`targets`, …). That is a **new migration** (append to `MIGRATIONS`; never edit migration 1) and is the
reason the "typed row models" cleanup was deferred to Phase 3 — the row shapes change here.
