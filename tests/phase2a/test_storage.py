import os
import sqlite3
import pytest
from app import storage, config


def test_schema_creates_all_tables(app_data_dir):
    key = os.urandom(32)
    conn = storage.connect(key)
    storage.init_schema(conn)
    names = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {"datasets", "cdr_records", "targets", "analysis_results", "audit_log"} <= names
    conn.close()


def test_db_file_is_encrypted_on_disk(app_data_dir):
    key = os.urandom(32)
    conn = storage.connect(key)
    storage.init_schema(conn)
    conn.close()

    raw = config.db_path().read_bytes()
    # A plaintext SQLite file begins with this magic string; an encrypted one must not.
    assert not raw.startswith(b"SQLite format 3\x00")

    # Plain sqlite3 (no key) cannot read an encrypted DB.
    with pytest.raises(sqlite3.DatabaseError):
        bad = sqlite3.connect(config.db_path())
        bad.execute("SELECT name FROM sqlite_master").fetchall()


def test_foreign_keys_enforced(app_data_dir):
    key = os.urandom(32)
    conn = storage.connect(key)
    storage.init_schema(conn)
    with pytest.raises(Exception):
        conn.execute(
            "INSERT INTO targets (name, dataset_id, phone_number, created_at) "
            "VALUES (?, ?, ?, ?)",
            ("x", 999, "01000001", "2026-01-01T00:00:00+00:00"),
        )
        conn.commit()
    conn.close()
