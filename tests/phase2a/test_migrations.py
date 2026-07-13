"""Tests for the versioned schema-migration seam (app/infra/migrations.py, ADR 0002)."""

import os

import pytest

from app.infra import migrations, storage

_BASELINE_TABLES = {"datasets", "cdr_records", "targets", "analysis_results", "audit_log"}
_LATEST = migrations.MIGRATIONS[-1][0]


def _key():
    return os.urandom(32)


def _tables(conn):
    return {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }


def test_fresh_install_creates_tables_and_stamps_version(app_data_dir):
    conn = storage.connect(_key())
    result = migrations.migrate(conn)
    assert _BASELINE_TABLES <= _tables(conn)
    assert result == _LATEST
    assert migrations.current_version(conn) == _LATEST
    conn.close()


def test_migrate_is_idempotent(app_data_dir):
    conn = storage.connect(_key())
    migrations.migrate(conn)
    # Second run is a no-op: version unchanged, no error.
    assert migrations.migrate(conn) == _LATEST
    assert migrations.current_version(conn) == _LATEST
    conn.close()


def test_adopts_matching_v0_database(app_data_dir):
    # Simulate a pre-versioning install: baseline tables present, user_version still 0.
    conn = storage.connect(_key())
    conn.executescript(migrations._BASELINE)
    conn.commit()
    assert migrations.current_version(conn) == 0
    assert _BASELINE_TABLES <= _tables(conn)

    # Adoption stamps it to v1, then the runner carries it on to the latest
    # migration in the same pass (migration 2 adds the saved-export tables).
    assert migrations.migrate(conn) == _LATEST
    assert migrations.current_version(conn) == _LATEST
    assert _BASELINE_TABLES <= _tables(conn)
    assert {"saved_pair_matches", "saved_tallies"} <= _tables(conn)
    conn.close()


def test_rejects_drifted_v0_database(app_data_dir):
    # A v0 DB whose schema does not match the baseline fingerprint must not be stamped.
    conn = storage.connect(_key())
    conn.executescript("CREATE TABLE datasets (id INTEGER PRIMARY KEY, name TEXT);")
    conn.commit()
    assert migrations.current_version(conn) == 0

    with pytest.raises(migrations.SchemaMismatchError):
        migrations.migrate(conn)
    # Left untouched — not stamped.
    assert migrations.current_version(conn) == 0
    conn.close()


def test_rejects_v0_with_same_columns_but_weaker_constraints(app_data_dir):
    # Codex's blocker: same table + column names as the baseline, but no NOT NULL /
    # FK / UNIQUE and no index. Migration 1's IF NOT EXISTS could not repair these
    # tables, so adoption must be rejected, not silently stamped v1.
    weakened = """
    CREATE TABLE datasets (id INTEGER PRIMARY KEY, name TEXT, filename TEXT,
        imported_at TEXT, row_count INTEGER, skipped_count INTEGER);
    CREATE TABLE cdr_records (id INTEGER PRIMARY KEY, dataset_id INTEGER,
        phone_number TEXT, imei TEXT, area TEXT, timestamp TEXT, call_type INTEGER,
        duration_seconds INTEGER, other_party TEXT, other_imei TEXT, other_area TEXT);
    CREATE TABLE targets (id INTEGER PRIMARY KEY, name TEXT, dataset_id INTEGER,
        phone_number TEXT, created_at TEXT);
    CREATE TABLE analysis_results (id INTEGER PRIMARY KEY, target_id INTEGER,
        created_at TEXT, result_json TEXT);
    CREATE TABLE audit_log (id INTEGER PRIMARY KEY, ts TEXT, username TEXT,
        event_type TEXT, detail TEXT);
    """
    conn = storage.connect(_key())
    conn.executescript(weakened)
    conn.commit()
    assert migrations.current_version(conn) == 0
    assert _BASELINE_TABLES <= _tables(conn)  # all tables present with matching column names

    with pytest.raises(migrations.SchemaMismatchError):
        migrations.migrate(conn)
    assert migrations.current_version(conn) == 0
    conn.close()


def test_rejects_v0_with_extra_trigger(app_data_dir):
    # Exact baseline tables/index PLUS an extra trigger. A trigger can change future
    # writes, so adoption must reject it rather than stamp v1 (Codex re-review blocker).
    conn = storage.connect(_key())
    conn.executescript(migrations._BASELINE)
    conn.executescript(
        "CREATE TRIGGER t_extra AFTER INSERT ON datasets "
        "BEGIN UPDATE datasets SET name = name; END;"
    )
    conn.commit()
    assert migrations.current_version(conn) == 0
    assert _BASELINE_TABLES <= _tables(conn)  # tables/index identical to baseline

    with pytest.raises(migrations.SchemaMismatchError):
        migrations.migrate(conn)
    assert migrations.current_version(conn) == 0
    conn.close()


def test_rejects_v0_with_extra_view(app_data_dir):
    conn = storage.connect(_key())
    conn.executescript(migrations._BASELINE)
    conn.executescript("CREATE VIEW v_extra AS SELECT id FROM datasets;")
    conn.commit()
    assert migrations.current_version(conn) == 0

    with pytest.raises(migrations.SchemaMismatchError):
        migrations.migrate(conn)
    assert migrations.current_version(conn) == 0
    conn.close()


def test_rejects_schema_too_new(app_data_dir):
    conn = storage.connect(_key())
    conn.execute(f"PRAGMA user_version = {_LATEST + 5}")
    with pytest.raises(migrations.SchemaTooNewError):
        migrations.migrate(conn)
    conn.close()


def test_failed_migration_rolls_back_atomically(app_data_dir):
    conn = storage.connect(_key())
    # v2 fails partway (creates _probe, then re-creates it -> error). The DDL and the
    # version bump share one transaction, so both must roll back together.
    bad_v2 = "CREATE TABLE _probe (id INTEGER PRIMARY KEY);\nCREATE TABLE _probe (id INTEGER);"
    with pytest.raises(Exception):
        migrations.migrate(conn, migrations=[(1, migrations._BASELINE), (2, bad_v2)])

    # Migration 1 committed; migration 2 rolled back entirely.
    assert migrations.current_version(conn) == 1
    assert "_probe" not in _tables(conn)
    assert _BASELINE_TABLES <= _tables(conn)
    conn.close()


def test_forward_migration_applies_and_bumps(app_data_dir):
    conn = storage.connect(_key())
    good_v2 = "CREATE TABLE _probe (id INTEGER PRIMARY KEY);"
    chain = [(1, migrations._BASELINE), (2, good_v2)]

    assert migrations.migrate(conn, migrations=chain) == 2
    assert migrations.current_version(conn) == 2
    assert "_probe" in _tables(conn)

    # Re-running the same chain is a no-op.
    assert migrations.migrate(conn, migrations=chain) == 2
    conn.close()


def test_migration_versions_are_contiguous_from_one():
    versions = [v for v, _ in migrations.MIGRATIONS]
    assert versions == list(range(1, len(versions) + 1))
