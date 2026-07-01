# AGENTS.md — start here

This repo is worked on by two AI coding agents (**Claude Code** and **Codex**) plus the human
(**Nadim**). Git is the only shared memory. Read these three docs before doing anything:

1. **`COLLAB.md`** — the two-agent protocol *and* the authoritative architecture rules
   (layers, invariants, contract names). This is the ground truth.
2. **`HANDOFF.md`** — the running state; **read the top entry first** for where things stand right now.
3. **`CLAUDE.md`** — the same architecture written as project guidance, plus "Where does X go?".

`COLLAB.md` holds stable rules; `HANDOFF.md` holds changing status. If they disagree on *status*,
`HANDOFF.md` wins.

## Non-negotiables (full detail in `COLLAB.md` / `CLAUDE.md`)

- **Phase 1 (`phase1_cdr/`) is FROZEN.** Never edit it. Reach it only through `app/infra/phase1.py`.
  Check `git diff --stat main -- phase1_cdr/` is empty before every commit.
- **Never commit straight to `main`.** Work on `codex/<task>` (Codex) or `claude/<task>` (Claude).
  The *other* agent reviews the branch diff. **Only Nadim merges to `main`.**
- **Prefix commits** so authorship is obvious: `codex: <what>` / `claude: <what>`.
- **Commit before handing off** — uncommitted work is invisible to the other agent. When you switch
  agents, tell the new one the other just pushed, so it re-reads git instead of trusting its snapshot.

## Architecture — layered, package-per-domain modular monolith (ADR 0001, done & merged)

The backend `app/` reorg is **complete**; the tree already matches the target. All new work targets it.

**Layer rule:** a higher layer may import a lower one, **never the reverse** —
APPLICATION → DOMAIN → AUDIT → SUPPORT → INFRA. (The `api` package spans layers on purpose:
`api.system` is APPLICATION; `api.guards/errors/responses` are SUPPORT.)

**Core invariants:**
1. Routes never write SQL — call the domain `repo`.
2. Repos never commit — the route owns the unit-of-work (`repo` → `audit.write_audit` → `commit`/`rollback`).
3. Repos take a `conn`, return dicts, import `infra` only — never `audit`, `api`, or `flask`.
4. No domain imports another domain's internals.
5. Phase 1 only via `infra/phase1.py`.
6. Auth identity via `api.guards.current_username()` — never `current_app.config["USERNAME"]` directly.

**These boundaries are CI-enforced** — import-linter contracts in `pyproject.toml`
(*Layered architecture*, *Domains are independent*, *Phase 1 only via infra.phase1*,
*Repos import neither audit nor api*) plus AST tests in `tests/architecture/`. A violation fails the
`boundaries` CI job (`lint-imports`) regardless of intent, so don't rely on memory alone — but don't
fight it either: if a change wants to cross a boundary, that's a design smell, revisit the placement.

## Running things

- Backend tests: `pytest tests/phase2a tests/architecture phase1_cdr/tests`
- Lint: `ruff check app tests main.py`
- Boundaries: `lint-imports` (runs in CI on ubuntu x64; grimp has no win_arm64 wheel).
- Desktop app: `python main.py`

This project is a **synthetic-data CS portfolio project** — no real telecom data, no network/surveillance
use. Don't add features that only make sense for real/live data or multi-tenant deployment; mark such
ideas design-only.
