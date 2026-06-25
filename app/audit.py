"""Audit-log writer. Never logs passwords or keys."""

from __future__ import annotations

import json
from datetime import datetime, timezone

SETUP = "SETUP"
LOGIN_SUCCESS = "LOGIN_SUCCESS"
LOGIN_FAIL = "LOGIN_FAIL"
LOGOUT = "LOGOUT"
IMPORT = "IMPORT"
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
