"""Versioned schema migrations for the encrypted DB — the single evolution seam.

The applied schema version is tracked in SQLite's built-in ``PRAGMA user_version``:
an application-reserved integer stored in the database header, so SQLCipher encrypts
it like the rest of the file and no extra table is needed. ``user_version`` is a
*cursor*, not an audit log — if migration history is ever required, add a
``schema_migrations`` table as a complement, never a replacement.

Migration 1 IS the Phase 2A baseline schema, verbatim and ``IF NOT EXISTS``, so a
fresh database and an exact Phase-2A database both converge on it. A pre-versioning
install (tables present, ``user_version == 0``) is *adopted* into versioning, but
only after its schema is validated against the baseline fingerprint — a drifted or
partial database fails loudly rather than being silently stamped v1.

Each migration's DDL and its version bump run inside one explicit ``BEGIN IMMEDIATE
… COMMIT`` so a crash can never leave DDL applied with the version unstamped (or the
reverse). This module is pure INFRA: it imports nothing higher and takes the open
connection as an argument.
"""

from __future__ import annotations

from sqlcipher3 import dbapi2 as sqlcipher

# --- Migration 1: the Phase 2A baseline (was storage.SCHEMA_SQL, kept byte-identical) ---
_BASELINE = """
CREATE TABLE IF NOT EXISTS datasets (
  id            INTEGER PRIMARY KEY,
  name          TEXT NOT NULL,
  filename      TEXT NOT NULL,
  imported_at   TEXT NOT NULL,
  row_count     INTEGER NOT NULL,
  skipped_count INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS cdr_records (
  id               INTEGER PRIMARY KEY,
  dataset_id       INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
  phone_number     TEXT NOT NULL,
  imei             TEXT,
  area             TEXT NOT NULL,
  timestamp        TEXT NOT NULL,
  call_type        INTEGER NOT NULL,
  duration_seconds INTEGER NOT NULL,
  other_party      TEXT,
  other_imei       TEXT,
  other_area       TEXT
);

CREATE INDEX IF NOT EXISTS idx_records_dataset_phone
  ON cdr_records(dataset_id, phone_number);

CREATE TABLE IF NOT EXISTS targets (
  id           INTEGER PRIMARY KEY,
  name         TEXT NOT NULL,
  dataset_id   INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
  phone_number TEXT NOT NULL,
  created_at   TEXT NOT NULL,
  UNIQUE(dataset_id, phone_number)
);

CREATE TABLE IF NOT EXISTS analysis_results (
  id          INTEGER PRIMARY KEY,
  target_id   INTEGER NOT NULL REFERENCES targets(id) ON DELETE CASCADE,
  created_at  TEXT NOT NULL,
  result_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
  id         INTEGER PRIMARY KEY,
  ts         TEXT NOT NULL,
  username   TEXT NOT NULL,
  event_type TEXT NOT NULL,
  detail     TEXT
);
"""

# --- Migration 2: saved report items (contact matcher + explorer tallies) ---
# Click-to-save export staging: the export workbook copies these stored rows and
# never recomputes. Pair identity is order-normalized by the writing repo
# (target_a_id < target_b_id) so A<->B and B<->A hit the same UNIQUE slot.
_SAVED_EXPORTS = """
CREATE TABLE IF NOT EXISTS saved_pair_matches (
  id          INTEGER PRIMARY KEY,
  dataset_id  INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
  target_a_id INTEGER NOT NULL REFERENCES targets(id) ON DELETE CASCADE,
  target_b_id INTEGER NOT NULL REFERENCES targets(id) ON DELETE CASCADE,
  created_at  TEXT NOT NULL,
  result_json TEXT NOT NULL,
  UNIQUE(target_a_id, target_b_id)
);

CREATE TABLE IF NOT EXISTS saved_tallies (
  id           INTEGER PRIMARY KEY,
  target_id    INTEGER NOT NULL REFERENCES targets(id) ON DELETE CASCADE,
  created_at   TEXT NOT NULL,
  filters_json TEXT NOT NULL,
  filter_label TEXT NOT NULL,
  tally_json   TEXT NOT NULL
);
"""

# Ordered (version, ddl) pairs, contiguous from 1. Append new migrations; never edit
# or reorder a released one (it may already be applied to installed databases).
MIGRATIONS: list[tuple[int, str]] = [
    (1, _BASELINE),
    (2, _SAVED_EXPORTS),
]

class MigrationError(RuntimeError):
    """Base class for migration-seam failures."""


class SchemaTooNewError(MigrationError):
    """The database's user_version is newer than any migration this code knows."""


class SchemaMismatchError(MigrationError):
    """A pre-versioning (v0) database's schema does not match the baseline fingerprint."""


def current_version(conn) -> int:
    """The schema version recorded in the database header."""
    return conn.execute("PRAGMA user_version").fetchone()[0]


def _table_names(conn) -> set[str]:
    return {
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }


def _normalize_ddl(sql: str) -> str:
    # Collapse every run of whitespace so formatting differences don't matter; the
    # comparison still reflects each column, type, and constraint in the DDL text.
    return " ".join(sql.split())


def _schema_fingerprint(conn) -> dict[str, str]:
    """Object name -> normalized CREATE DDL for every user-defined schema object.

    Covers all sqlite_master object types — tables, indexes, triggers, AND views — so an
    adopted v0 DB cannot carry an extra trigger/view (a trigger can alter future writes).
    `sql IS NOT NULL` drops auto-created indexes (sqlite_autoindex_*, whose UNIQUE clause
    is already captured in the owning table's DDL); `name NOT LIKE 'sqlite_%'` drops
    internal objects.
    """
    rows = conn.execute(
        "SELECT name, sql FROM sqlite_master "
        "WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {r[0]: _normalize_ddl(r[1]) for r in rows}


def _baseline_fingerprint() -> dict[str, str]:
    """The fingerprint migration 1 produces, computed via a throwaway in-memory DB so
    SQLite itself canonicalizes the DDL — no brittle hand-maintained constants."""
    ref = sqlcipher.connect(":memory:")
    try:
        ref.executescript(_BASELINE)
        return _schema_fingerprint(ref)
    finally:
        ref.close()


def _assert_matches_baseline(conn) -> None:
    """Raise SchemaMismatchError unless `conn`'s schema is exactly the v1 baseline.

    Guards adoption of a v0 (pre-versioning) database. Compares the full CREATE DDL —
    columns, types, NOT NULL / FK / UNIQUE, and indexes — not just column names, because
    migration 1's `IF NOT EXISTS` cannot repair a same-columns-but-weaker-constraints
    table once it is stamped v1.
    """
    actual = _schema_fingerprint(conn)
    expected = _baseline_fingerprint()
    if actual != expected:
        unexpected = sorted(set(actual) - set(expected))
        missing = sorted(set(expected) - set(actual))
        differing = sorted(n for n in set(actual) & set(expected) if actual[n] != expected[n])
        raise SchemaMismatchError(
            "cannot adopt v0 database: schema does not match the v1 baseline "
            f"(unexpected={unexpected}, missing={missing}, differing={differing})"
        )


def migrate(conn, migrations: list[tuple[int, str]] = MIGRATIONS) -> int:
    """Apply every pending migration in order and return the resulting version.

    `migrations` is injectable so tests can exercise the runner without coupling to
    the real migration count.
    """
    latest = migrations[-1][0] if migrations else 0
    current = current_version(conn)

    if current > latest:
        raise SchemaTooNewError(
            f"database user_version {current} is newer than latest known migration {latest}"
        )

    # A non-empty database still at v0 predates versioning: validate before adopting.
    if current == 0 and _table_names(conn):
        _assert_matches_baseline(conn)

    for version, ddl in migrations:
        if version <= current:
            continue
        # DDL + version bump are one transaction. `version` is a trusted int from our
        # own list (PRAGMA values cannot be parameter-bound). executescript() commits
        # any pending tx first and adds no transaction control of its own, so the
        # BEGIN/COMMIT below is what makes this migration atomic.
        script = f"BEGIN IMMEDIATE;\n{ddl}\nPRAGMA user_version = {version};\nCOMMIT;"
        try:
            conn.executescript(script)
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise
        current = version

    return current
