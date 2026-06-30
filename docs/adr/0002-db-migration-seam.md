# ADR 0002 — DB migration seam

- **Status:** accepted
- **Date:** 2026-06-30
- **Deciders:** Nadim (merges); proposed by Claude, reviewed by Codex

## Context

The schema was created by a single inline `CREATE TABLE IF NOT EXISTS` block
(`app/infra/storage.py`) with **no version tracking**. ADR 0001 deferred migrations to
"first real install" and claimed `infra/migrations.py` was "the seam is ready" — but the
seam did not exist. Phase 3 (multi-user/admin/LAN) will add tables (`users`, `sessions`,
`roles`) and alter existing ones. `CREATE TABLE IF NOT EXISTS` silently does nothing to an
already-installed encrypted database, so the first Phase 3 schema change would have **no
upgrade path** for any existing DB. We build the seam now — while the schema is trivial and
behavior is frozen — so that claim becomes true and the risky part of Phase 3 is de-risked.

This is a synthetic-data, single-user desktop portfolio app; the seam is sized accordingly
(no Alembic, no migration framework).

## Decision

Add `app/infra/migrations.py`, a minimal versioned-migration runner. Rules for agents:

- **Version cursor = `PRAGMA user_version`.** SQLite reserves it for applications and stores
  it in the (SQLCipher-encrypted) DB header, so no extra table is needed. It is a cursor, not
  history; if migration history is ever needed, add a `schema_migrations` table as a
  *complement*, never a replacement.
- **`MIGRATIONS` is an append-only, contiguous-from-1 list of `(version, ddl)`.** Migration 1
  IS the Phase 2A baseline, verbatim and `IF NOT EXISTS`. Never edit or reorder a released
  migration — it may already be applied to installed databases.
- **Each migration is atomic with its version bump.** The DDL and `PRAGMA user_version = N`
  run inside one `BEGIN IMMEDIATE … COMMIT`, with `ROLLBACK` on exception. A crash can never
  leave DDL applied without the version stamped (or vice-versa). Do **not** stamp the version
  first. (`executescript()` only commits a pending tx and adds no transaction control of its
  own, hence the explicit transaction in the script.)
- **Two guards.** (1) `user_version` newer than the latest known migration → `SchemaTooNewError`.
  (2) A non-empty database still at `user_version == 0` (a pre-versioning install) is *adopted*
  only after its schema matches the baseline fingerprint; a drifted/partial DB raises
  `SchemaMismatchError` instead of being silently stamped v1. The fingerprint compares the **full
  normalized CREATE DDL** of every table and index (columns, types, NOT NULL / FK / UNIQUE,
  indexes) — not just column names — because migration 1's `IF NOT EXISTS` cannot repair a
  same-columns-but-weaker-constraints table once stamped. The expected fingerprint is computed from
  a throwaway in-memory DB so SQLite canonicalizes both sides (no hand-maintained constants).
- **`storage.init_schema` delegates to `migrations.migrate`.** Behavior is frozen: the
  fresh-install path produces the identical schema; the only new observable is
  `user_version == 1`.

## Consequences

- **Easier/safer:** Phase 3 schema changes are append-a-migration, not a rewrite; existing
  encrypted databases have a real, atomic, guarded upgrade path.
- **Giving up:** nothing observable today; one extra `PRAGMA user_version` read at schema init.
- **Defers — migrate-on-login (the one-line Phase 3 flip):** migrations run today only where
  `init_schema`/`migrate` is explicitly called (account creation), so a *fresh* DB is stamped
  but an *existing* DB is not auto-upgraded on login. Phase 3 activates auto-upgrade by adding
  `migrations.migrate(g.db)` in `app/api/guards.py` (`get_db()`), immediately after
  `storage.connect(key)` and before storing `g.db`. Left unwired now to keep this change
  behavior-frozen.

## Alternatives considered

- **`schema_migrations` table instead of `user_version`** — heavier; SQLite already reserves
  `user_version` for exactly this. Revisit only if audit-style migration history is required
  (then as a complement).
- **Stamp version, then apply DDL** — rejected: a crash between the two would make the app skip
  unapplied DDL. Atomic transaction is strictly safer.
- **Defer the whole seam to "first real install" (ADR 0001's original stance)** — rejected:
  building it while the schema is trivial is cheaper and removes the largest Phase 3 unknown.
- **An external migration framework (Alembic)** — overkill for a single-file synthetic DB.
