"""Single-account lifecycle: setup, authenticate, change-password.

Under the server-holds-key model (ADR 0003 part 2) the DB key is the server
master key, unlocked once at process start -- it is never derived from the user's
password and never written to disk. So the auth.json sidecar records only the
credential and holds NO key material:
  { username, bcrypt_hash, created_at }
Setup records the credential; the encrypted DB is built lazily by the first
get_db() via the migration seam. authenticate() verifies the credential only.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import tempfile
from datetime import datetime, timezone

from app.infra import config, crypto

logger = logging.getLogger(__name__)


class AccountExistsError(Exception):
    pass


class AuthError(Exception):
    pass


class PasswordTooLongError(Exception):
    """The password exceeds bcrypt's hard limit (see MAX_PASSWORD_BYTES)."""


# bcrypt rejects inputs longer than 72 bytes. Up to and including bcrypt 4.x this
# was a SILENT truncation; bcrypt >= 5.0 raises ValueError instead. We guard at
# this layer so the routes can return a clean 400 rather than a 500, independent
# of the installed bcrypt version.
MAX_PASSWORD_BYTES = 72


def _check_password_length(password: str) -> None:
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise PasswordTooLongError(
            f"password must be at most {MAX_PASSWORD_BYTES} bytes"
        )


def account_exists() -> bool:
    return config.auth_path().exists()


def _load() -> dict:
    with open(config.auth_path(), "r", encoding="utf-8") as fh:
        return json.load(fh)


def _save(record: dict) -> None:
    auth_path = config.auth_path()
    auth_dir = auth_path.parent
    auth_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=auth_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(record, fh, indent=2)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())  # durably persist contents before the swap
        os.replace(tmp_path, auth_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            logger.warning("could not remove temp auth file %s after a failed save", tmp_path)
        raise


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_account(username: str, password: str) -> None:
    """Create the single local account. The DB key is the server master key
    (bootstrap, ADR 0003 pt2), so setup only records the credential; the DB itself
    is built lazily by the first get_db() via the migration seam."""
    if account_exists():
        raise AccountExistsError("an account already exists")
    _check_password_length(password)
    _save({
        "username": username,
        "bcrypt_hash": crypto.hash_password(password),
        "created_at": _now(),
    })


def authenticate(username: str, password: str) -> None:
    """Verify credentials against auth.json. Raises AuthError on any mismatch.
    No DB key is derived -- the server already holds the master key."""
    if not account_exists():
        raise AuthError("no account")
    try:
        rec = _load()
        stored_username = rec["username"]
        bcrypt_hash = rec["bcrypt_hash"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        raise AuthError("bad credentials") from None
    try:
        username_ok = hmac.compare_digest(
            username.encode("utf-8"), stored_username.encode("utf-8"))
        password_ok = crypto.verify_password(password, bcrypt_hash)
    except (AttributeError, TypeError, ValueError):
        raise AuthError("bad credentials") from None
    if not (username_ok and password_ok):
        raise AuthError("bad credentials")


def change_password(old_password: str, new_password: str) -> None:
    if not account_exists():
        raise AuthError("no account")
    _check_password_length(new_password)
    try:
        rec = _load()
        username = rec["username"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        raise AuthError("bad credentials") from None
    authenticate(username, old_password)  # raises AuthError if wrong
    rec["bcrypt_hash"] = crypto.hash_password(new_password)
    _save(rec)
