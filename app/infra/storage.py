"""SQLCipher-backed storage: encrypted connection + schema.

The database key is the raw 32-byte value produced at setup (see account.py).
It is passed to SQLCipher as a hex blob via `PRAGMA key`, which must run before
any other statement on the connection.
"""

from __future__ import annotations

from sqlcipher3 import dbapi2 as sqlcipher

from app.infra import config, migrations

# Back-compat re-export: the baseline DDL now lives in migrations.py as migration 1.
# Kept here because older docs/tests referenced storage.SCHEMA_SQL.
SCHEMA_SQL = migrations._BASELINE


def connect(db_key: bytes) -> sqlcipher.Connection:
    conn = sqlcipher.connect(str(config.db_path()))
    # PRAGMA key MUST be the first statement. Raw key as a hex blob (x'..').
    conn.execute(f"PRAGMA key = \"x'{db_key.hex()}'\"")
    # Each request opens its own connection and the desktop server is threaded,
    # so two requests can write at once. Without a busy_timeout SQLite's default
    # is 0 ms -- the second writer instantly raises "database is locked". Wait
    # instead of failing the request.
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlcipher.Row
    return conn


def init_schema(conn) -> None:
    # Delegates to the versioned migration runner (ADR 0002). On a fresh DB this
    # applies the baseline and stamps user_version = 1; the runner commits per
    # migration, so the connection is left committed exactly as before.
    migrations.migrate(conn)
