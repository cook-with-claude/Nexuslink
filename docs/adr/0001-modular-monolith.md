# ADR 0001 — Reorganize the backend into a layered modular monolith

- **Status:** accepted
- **Date:** 2026-06-30
- **Deciders:** Nadim (approved the plan); proposed by Claude, reviewed by Codex (SOUND-WITH-CHANGES)

## Context

Phase 2 is complete and merged. **Phase 3 is a multi-user platform with admin roles, connected
over LAN** — the hardest phase. The Phase 2A backend was built for a *single* local user, and two
of its facts directly contradict multi-user:

- **Process-global auth state** — `current_app.config["DB_KEY"]` / `["USERNAME"]`. One key slot and
  one username slot for the whole process; it cannot represent two users at once.
- **Single-account model** — `account.py` is hard-wired to exactly one `auth.json`.

Building Phase 3 on those means stacking the hardest features on a foundation we already know we
will rip out, then reorganizing a much larger, networked, concurrent codebase. The backend is
currently small (~1,100 LoC across 13 modules), with **117 passing tests** pinning behavior and
Phase 1 byte-frozen. Reorganizing is cheapest and safest *now*.

Constraints: this is a **synthetic-data CS portfolio** project (no real telecom data, no operational
surveillance use); **Phase 1 (`phase1_cdr/`) is frozen**; the repo is worked by **two agents who
cannot see each other's chats** (git is the only shared memory; only Nadim merges).

## Decision

Reorganize `app/` into a **layered, package-per-domain modular monolith**, **behavior-frozen**
(no functional change — identical SQL, statement order, commit points, and HTTP responses), in
small incremental steps with the test suite green between each.

**Layers (a higher layer may import a lower one; never the reverse):**

```
APPLICATION : api.system, <domain>.routes
DOMAIN/DATA : <domain>.account / .repo / .validation / .bridge
AUDIT       : audit.log
SUPPORT     : api.guards, api.errors  (use api.responses + infra)
              api.responses           (flask only)
INFRA       : infra.config, infra.crypto, infra.storage, infra.phase1
```

**Invariants (enforced — see "Mechanical enforcement"):**

1. **Routes never write SQL.** They call their domain's `repo`.
2. **Repos never commit.** The route owns the unit-of-work (`repo` calls → `audit.write_audit` →
   `conn.commit()` / `conn.rollback()`).
3. **Repos take a `conn`, return plain dicts, and import `infra` only** — never `audit`, `api`, or
   `flask`.
4. **No domain imports another domain's internals.** Cross-domain needs go through a shared module.
5. **Phase 1 is reached only through `infra/phase1.py`** — the single seam to `phase1_cdr/`.
6. **Auth/session state moves to a per-session context in Phase 3 — never process globals.** Until
   then, all reads go through `api.guards.current_username()` (one function to swap later).

**Scope boundary:** this reorg is structural only. The multi-user auth/session rework and
multi-account model are the **first Phase 3 increment**, done *inside* this structure.

## Mechanical enforcement

Prose does not stop two blind agents from eroding boundaries; CI does.

- **import-linter** contract in CI (layers + `containers` for routes-above-repo per domain +
  `independence` across domains + a `forbidden` contract for Phase 1). Every contract is validated
  with a deliberate bad import before the CI job is made enforcing.
- **AST architecture tests** (`tests/architecture/`) for what import-linter cannot express: no SQL
  execution in `*/routes.py`; no `commit()`/`rollback()` in `*/repo.py`; no `flask` import in
  `*/repo.py`.

### import-linter contract (as-built — `[tool.importlinter]` in `pyproject.toml`, enforcing)

Activated in Step 9 once every package existed. Four contracts, run by the CI `boundaries`
job (`lint-imports`) on ubuntu x64 — grimp has no win_arm64 wheel, so it does not run on the
ARM64 dev machine:

1. **`layers`** (module-level, highest first): `api.system | <domain>.routes` ; `<domain>.account/
   .repo/.validation/.bridge` ; `audit` ; `api.guards | api.errors` ; `api.responses` ; `infra`.
   (`audit` and `infra` are named as packages so intra-package imports are allowed; `api` spans
   layers because `system` is APPLICATION while `responses/guards/errors` are SUPPORT.)
2. **`independence`**: `app.auth`, `app.datasets`, `app.targets`, `app.analysis` (auth is a domain too).
3. **`forbidden` (Phase 1)**: `include_external_packages = true`, `allow_indirect_imports = true`;
   source = every app module except `app.infra.phase1`; `forbidden_modules = detection, loader`
   (allow_indirect_imports keeps the legitimate `bridge -> infra.phase1 -> detection` seam green).
4. **`forbidden` (repos)**: `app.*.repo` must not import `app.audit` or `app.api`. The
   no-`flask`-in-repos rule is enforced by the AST architecture test in `tests/architecture/`
   (`flask` is external, so keeping it out of this contract avoids `include_external_packages` here).

The global `layers` contract already places every `<domain>.routes` above every `<domain>.repo`,
so the routes-above-repo rule did not need a separate `containers` contract.

## Consequences

- **Easier/safer:** clean seams for the Phase 3 multi-user/admin/LAN build; the shared-DB-vs-per-user
  data decision lands in `infra/storage.py` + an ADR and does **not** ripple through domains because
  `repo.py` is the single data-access seam; boundaries are CI-enforced.
- **Cost:** broad (but mechanical) import churn; ~10 small PRs; updates to test import paths.
- **Defers:** multi-user auth/session and multi-account → first Phase 3 increment; rate-limiting →
  only if login becomes network-reachable (and even then, synthetic/portfolio only).
  (DB migrations: the `infra/migrations.py` seam is now **built** — see ADR 0002. Authoring the
  first real schema change and wiring migrate-on-login remain Phase 3 work.)

## Alternatives considered

- **Build Phase 3 first, reorganize after** — rejected: builds the hardest features on a foundation we
  will replace, then forces a riskier reorg of a much larger codebase.
- **Full DI container / abstract interfaces now** — rejected as premature; single implementations make
  them indirection with no payoff. Documented as an enterprise design path, not built.
- **Lighter flat split (no per-domain packages)** — rejected: the flat namespace gets crowded once
  Phase 3 adds `users/`, `admin/`, roles.
