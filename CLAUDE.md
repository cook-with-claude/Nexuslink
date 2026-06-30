# CLAUDE.md — project guidance

La Passion infers a subscriber's likely **home / work / frequent** areas from Call Detail Records.
It is a **synthetic-data CS portfolio project** — no real telecom data, no network access, no
operational/surveillance use. A Flask + PyWebView desktop app over a SQLCipher-encrypted DB, with a
vanilla no-build SPA frontend.

## Hard rules (do not violate)

- **Phase 1 (`phase1_cdr/`) is FROZEN.** Never edit it. It is independently validated in CI. Reach it
  only through `app/infra/phase1.py` (the single seam). Check `git diff --stat <base> -- phase1_cdr/`
  is empty before every commit.
- **Synthetic data only.** Do not add features that only make sense for real/live data, networked
  multi-tenant deployment, or surveillance. If asked, mark them design-only.
- **Two-agent workflow.** Git is the only shared memory. Work on a `claude/<task>` branch; commit
  before handing off; **never merge to `main`** — only Nadim merges. See `COLLAB.md`; running state
  is in `HANDOFF.md` (top entry).

## Architecture — layered modular monolith

> **Migration in progress (ADR 0001).** The backend is being reorganized from flat `app/*.py` into the
> layered package structure below, behavior-frozen, in steps. During the migration the on-disk tree is
> converging toward this target — check git / `HANDOFF.md` for the current step. New work must target
> this structure.

```
app/
  __init__.py   create_app() factory + blueprint registration ONLY
  api/          web layer — responses.py, guards.py, errors.py (SUPPORT); system.py (APPLICATION)
  auth/         account.py (DOMAIN), routes.py (APPLICATION)        [session.py in Phase 3]
  datasets/     repo.py, validation.py (DOMAIN); routes.py (APPLICATION)
  targets/      repo.py (DOMAIN); routes.py (APPLICATION)
  analysis/     repo.py, bridge.py (DOMAIN); routes.py (APPLICATION)
  audit/        log.py
  infra/        config.py, crypto.py, storage.py, phase1.py  (no domain logic, no Flask)
  ui.py / web/  SPA shell + assets (UNCHANGED; ui registered in main.py, not create_app)
```

**Layer rule:** a higher layer may import a lower one, never the reverse —
APPLICATION → DOMAIN → AUDIT → SUPPORT → INFRA. (The `api` package spans layers: its `system.py`
route is APPLICATION; its `responses/guards/errors` helpers are SUPPORT.)

**Invariants (CI-enforced via import-linter + `tests/architecture/`):**
1. Routes never write SQL — call the domain `repo`.
2. Repos never commit — the route owns the unit-of-work (`repo` calls → `audit.write_audit` →
   `conn.commit()`/`rollback()`).
3. Repos take a `conn`, return dicts, import `infra` only — never `audit`, `api`, or `flask`.
4. No domain imports another domain's internals.
5. Phase 1 only via `infra/phase1.py`.
6. Auth identity is read via `api.guards.current_username()` — never `current_app.config["USERNAME"]`
   directly (Phase 3 swaps the accessor's body for per-session context).

### Where does X go?
- New endpoint in an existing domain → extend `repo.py` (if data access) + a thin handler in
  `routes.py`; tests under `tests/phase2a/<domain>/`.
- New domain (e.g. `users/`, `admin/`) → `app/<domain>/{__init__,repo,routes}.py` (+`service.py` if
  logic exists); register the blueprint; add it to the import-linter layer/independence set; tests dir;
  an ADR if the decision is notable.
- New cross-cutting HTTP helper → `app/api/`.
- New infrastructure (DB, crypto, paths, migrations) → `app/infra/`.

## Running things
- Backend tests: `pytest tests/phase2a phase1_cdr/tests` (currently **117 passing**).
- Lint: `ruff check app tests main.py` (config in `pyproject.toml`; excludes `phase1_cdr/`, `vendor/`).
- Boundaries: `lint-imports` (import-linter) — enforcing from the final reorg step.
- Desktop app: `python main.py` (needs the .NET Desktop Runtime on Windows; see `README.md`).

## Key docs
- `COLLAB.md` — two-agent protocol + the architecture rules (agent-neutral).
- `HANDOFF.md` — running intent log (newest on top); read the top entry first.
- `docs/adr/` — Architecture Decision Records (start at `0001-modular-monolith.md`).
- `EXPERT_BRIEF.md` — the domain/method brief (the algorithm and its assumptions).
