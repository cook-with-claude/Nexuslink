"""SQLCipher-backed storage: encrypted connection + schema.

The database key is the raw 32-byte value produced at setup (see account.py).
It is passed to SQLCipher as a hex blob via `PRAGMA key`, which must run before
any other statement on the connection.
"""

from __future__ import annotations

from sqlcipher3 import dbapi2 as sqlcipher

from app import config

SCHEMA_SQL = """
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


def connect(db_key: bytes):
    conn = sqlcipher.connect(str(config.db_path()))
    conn.row_factory = sqlcipher.Row
    # PRAGMA key MUST be the first statement. Raw key as a hex blob (x'..').
    conn.execute(f"PRAGMA key = \"x'{db_key.hex()}'\"")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()
