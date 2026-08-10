# CLAUDE.md — project guidance

Nexuslink infers a subscriber's likely **home / work / frequent** areas from Call Detail Records.
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

> **This is the live structure (ADR 0001 — done, merged).** The backend reorg from flat `app/*.py`
> into the layered package-per-domain layout below is **complete** and behavior-frozen; the on-disk
> tree already matches this target. All new work targets this structure, and the boundaries are
> **CI-enforced** (import-linter contracts + `tests/architecture/` — see Invariants below), so a
> violation fails CI regardless of intent.

```
app/
  __init__.py   create_app() factory + blueprint registration ONLY
  api/          web layer — responses.py, guards.py, errors.py (SUPPORT); system.py (APPLICATION)
  auth/         account.py (DOMAIN), routes.py (APPLICATION)        [session.py in Phase 3]
  datasets/     repo.py, validation.py (DOMAIN); routes.py (APPLICATION)
  targets/      repo.py (DOMAIN); routes.py (APPLICATION)
  analysis/     repo.py, bridge.py (DOMAIN); routes.py (APPLICATION)
  matching/     repo.py, gates.py (DOMAIN, gates is pure); service.py (verdicts) +
                ledger.py (the pair's RECORDS — own feature, same domain: it reuses the
                same facts + the same distinctive/common classifier, so labels can't drift);
                routes.py (APPLICATION)
  reporting/    export.py (DOMAIN); routes.py (APPLICATION) — cross-domain report composition,
                deliberately OUTSIDE the domain-independence contract (it reads analysis+matching)
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
- Backend tests: `pytest tests/phase2a tests/architecture phase1_cdr/tests` (currently **288 passing**;
  `tests/architecture/` holds the AST boundary checks).
- Frontend tests: the SPA is vanilla no-build JS, so there's no framework — `node --check` syntax-checks
  every module, and `node --test app/web/js/components.test.mjs` runs the behavioural smoke tests
  (Node's built-in runner; **38 currently**). Both run in the CI `frontend` job. Logic worth testing is
  extracted as a pure exported function (`bindingGates`, `filterLedgerRows`, `sortLedgerRows`) rather
  than tested through the minimal DOM shim. NOTE: a JS refactor that renames/removes an
  exported symbol can still break **pytest** — `tests/phase2a/test_ui.py` greps served JS for symbol
  needles, so grep `tests/` too before assuming "no Python touched → tests unaffected".
- Lint: `ruff check app tests main.py` (config in `pyproject.toml`; excludes `phase1_cdr/`, `vendor/`).
- Boundaries: `lint-imports` (import-linter) — **enforcing** (CI `boundaries` job). grimp has no
  win_arm64 wheel, so it can't run on native Windows; it runs in CI on ubuntu x64 (and locally in WSL).
- Security: the CI `security` job runs three scanners, all **enforcing**, all installable via
  `requirements-dev.txt` — `pip-audit --strict --no-deps -r constraints.txt` (known CVEs in the pinned
  runtime lock), `bandit -c pyproject.toml -r app main.py tools` (Python SAST, run at bandit's
  **strictest** setting — no severity/confidence filter), and `gitleaks git . --redact` (secrets
  across **all** git history, not just the tip). The workflow also ticks **weekly** (Mon 06:00 UTC) so
  a newly-disclosed CVE surfaces without anyone pushing. All 14 bandit findings are reviewed false
  positives carrying an inline `# nosec <ID>` with the reasoning directly above it — no check is
  skipped wholesale, so a genuinely new finding still fails the build. Bandit prints
  `nosec encountered (Bxxx), but no failed test` WARNING lines on stderr; those are **expected** (the
  price of precise per-id markers over blanket ones) and do not affect exit status — see the long
  comment in `[tool.bandit]`. Deliberately not a SaaS *lint aggregator* (DeepSource): ruff +
  import-linter + `tests/architecture/` already cover style and structure, so these three add only
  what nothing else checks, in-repo, with no third-party token on the repository.
- CodeQL: separate `.github/workflows/codeql.yml` (python + javascript-typescript, `build-mode: none`,
  `security-extended`), config in `.github/codeql/codeql-config.yml`. It adds **interprocedural
  dataflow / taint tracking**, which bandit structurally cannot do — bandit matches patterns within a
  statement, CodeQL follows a value across function boundaries. Free because the repo is **public**
  (2026-08-09); code scanning on a private repo needs a paid GitHub security SKU. Own workflow, not
  folded into `ci.yml`, because it needs `security-events: write` and `ci.yml` runs `contents: read`.
  Triggers on push/PR to `main` + weekly. `paths-ignore`s frozen `phase1_cdr/`, `vendor/`, `tests/`.
  This is CodeQL **advanced setup** (a workflow file we control) — ⚠️ never switch on "Default setup"
  in Settings → Code security, which conflicts with it and disables the workflow, silently dropping
  the frozen-`phase1_cdr` exclusion and the `security-extended` suite. Nothing to install: CodeQL is
  GitHub's own engine, the workflow *is* the setup.
- Also live on the public repo: **secret scanning + push protection** (a push containing a detected
  credential is blocked outright) and **Dependabot alerts + automated security updates**.
  `.coderabbit.yaml` is committed and carries this project's ADR-0001 invariants as
  `path_instructions`; the **GitHub App is installed** (2026-08-10, scoped to this repo only).
  ⚠️ CodeRabbit reads its config from a PR's **base branch**, so until `.coderabbit.yaml` is on
  `main` it reviews with stock defaults and none of the invariants apply.
  On Windows, prefix `pip-audit --desc on` with `PYTHONIOENCODING=utf-8` — its output contains `→`,
  which crashes the cp1252 console.
- Desktop app: `.venv\Scripts\python.exe main.py` (needs the .NET Desktop Runtime on Windows; see
  `README.md`). Import `sample_cdr_data.xlsx` (repo root) to seed data for manual testing. For the
  contact matcher, `sample_matcher_scenarios.xlsx` (strangers mode) + `sample_matcher_closeknit.xlsx`
  (close-knit mode) cover every outcome — expected results per pair in `docs/matcher-test-scenarios.md`;
  regenerate both via `tools/gen_matcher_scenarios.py` (it asserts the tables against the real engine).
- **Local testing:** as of 2026-07-04 native Windows **runs the full suite** (`.venv` Python 3.11.9,
  pandas 3.0.3 — the earlier Smart App Control / `tslib` block is gone): `.venv\Scripts\python.exe -m
  pytest tests/phase2a tests/architecture phase1_cdr/tests` → 288 passed (~73s). **WSL2** (Ubuntu, venv
  at `/root/lp-venv`) still works as a fallback; CI (Ubuntu) is the canonical gate. See the
  `local-testing-wsl` auto-memory.

## Key docs
- `HANDOFF.md` → **`▶ NEXT SESSION — START HERE`** block at the very top: outstanding actions,
  recommended next work, and the gotchas that bite. Read it before anything else.
- `COLLAB.md` — two-agent protocol + the architecture rules (agent-neutral). Includes the
  **enforced branch protection** on `main` (7 required checks; renaming a CI job makes `main`
  unmergeable until the protection contexts are updated too).
- `AGENTS.md` — onboarding pointer auto-read by Codex (mirrors the rules; points here + COLLAB/HANDOFF).
- `HANDOFF.md` — running intent log (newest on top); read the top entry first.
- `docs/reference/` — `api.md` (endpoint reference) + `schema.md` (DB schema mirror).
- `docs/phase3-surface.md` — the global-auth de-globalization inventory for the Phase 3 first move.
- `docs/superpowers/specs/2026-07-04-phase3-multiuser-platform-design.md` — **the approved Phase 3
  design** (brainstormed 2026-07-04): LAN multi-user server, server-holds-master-key, browser
  clients, admin/analyst RBAC, dataset-access approval, tamper-evident activity log, CA-issued
  HTTPS, TOTP MFA. Decomposed into small increments 3.1→3.7. Read this before writing any Phase 3 plan.
- `docs/superpowers/specs/2026-07-13-adaptive-matcher-gates.md` — the contact matcher's
  **dataset-adaptive distinctiveness** (strangers vs close-knit modes, commonality floor, cliff
  disclosure). Read alongside the 2026-07-12 matcher spec before touching `app/matching/gates.py`.
- `docs/adr/` — Architecture Decision Records (start at `0001-modular-monolith.md`; ADR 0002
  `db-migration-seam`, **activated by increment 3.1** — `migrations.migrate()` now runs in
  `get_db()` on login; ADRs 0003 server-key/auth, 0004 approval to be authored per Phase 3 increment).
- `EXPERT_BRIEF.md` — the domain/method brief (the algorithm and its assumptions).
