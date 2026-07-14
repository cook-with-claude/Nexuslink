"""Audit-log writer. Never logs passwords or keys."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from app.infra import config

logger = logging.getLogger(__name__)

SETUP = "SETUP"
LOGIN_SUCCESS = "LOGIN_SUCCESS"
LOGIN_FAIL = "LOGIN_FAIL"
LOGOUT = "LOGOUT"
IMPORT = "IMPORT"
DATASET_DELETE = "DATASET_DELETE"
DATASET_RENAME = "DATASET_RENAME"
TARGET_CREATE = "TARGET_CREATE"
TARGET_DELETE = "TARGET_DELETE"
TARGET_RENAME = "TARGET_RENAME"
ANALYSIS = "ANALYSIS"
EXPORT = "EXPORT"
CHANGE_PASSWORD = "CHANGE_PASSWORD"
# Saved-export staging (contact matcher + frequency explorer). Running a match
# or a tally is a read and is not audited; changing what the export will
# contain is a mutation and is.
PAIR_MATCH_SAVE = "PAIR_MATCH_SAVE"
PAIR_MATCH_DELETE = "PAIR_MATCH_DELETE"
TALLY_SAVE = "TALLY_SAVE"
TALLY_DELETE = "TALLY_DELETE"
LEDGER_SAVE = "LEDGER_SAVE"
LEDGER_DELETE = "LEDGER_DELETE"


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
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    except OSError:
        # Best-effort by contract (see docstring): an unwritable sidecar must not
        # turn the caller's 401 into a 500.
        logger.warning("could not record failed login to %s", path, exc_info=True)
