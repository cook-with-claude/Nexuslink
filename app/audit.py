"""Audit-log writer. Never logs passwords or keys."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from app.infra import config

SETUP = "SETUP"
LOGIN_SUCCESS = "LOGIN_SUCCESS"
LOGIN_FAIL = "LOGIN_FAIL"
LOGOUT = "LOGOUT"
IMPORT = "IMPORT"
DATASET_DELETE = "DATASET_DELETE"
TARGET_CREATE = "TARGET_CREATE"
TARGET_DELETE = "TARGET_DELETE"
ANALYSIS = "ANALYSIS"
CHANGE_PASSWORD = "CHANGE_PASSWORD"


def write_audit(conn, username: str, event_type: str, detail: dict | None = None) -> None:
    conn.execute(
        "INSERT INTO audit_log (ts, username, event_type, detail) VALUES (?, ?, ?, ?)",
        (
            datetime.now(timezone.utc).isoformat(),
            username,
            event_type,
            json.dumps(detail) if detail is not None else None,
        ),
    )


# Failed logins can't be written to the encrypted audit_log (no DB key without a
# successful unlock), so they go to this append-only plaintext sidecar. It holds
# no secrets -- only the attempt's time and the supplied username -- and json.dumps
# escapes the (attacker-controlled) username so it can't break the line format.
FAILED_LOGIN_FILE = "login_failures.log"


def write_failed_login(username: str) -> None:
    """Append a failed-login record to the plaintext sidecar.

    NOTE: this file is plaintext and NOT tamper-evident -- anyone who can write
    app-data can edit or delete it. It is a best-effort operational signal, not an
    authoritative audit source. Making it tamper-evident (HMAC/encryption) would
    require a key that lives outside editable app-data AND is available before the
    DB is unlocked, which this Phase 2A local-app threat model does not provide.
    """
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event_type": LOGIN_FAIL,
        "username": username,
    }
    path = config.app_data_dir() / FAILED_LOGIN_FILE
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
