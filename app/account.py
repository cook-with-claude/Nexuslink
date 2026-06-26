"""Single-account lifecycle: setup, authenticate, change-password.

Stores only non-secret material in the auth.json sidecar:
  { username, bcrypt_hash, kdf_salt, db_key_nonce, wrapped_db_key, created_at }
All binary fields are base64-encoded. The raw db_key is returned in-memory to
the caller (the Flask app holds it for the session) but never written to disk.
"""

from __future__ import annotations

import base64
import binascii
import hmac
import json
import os
import tempfile
from datetime import datetime, timezone

from cryptography.exceptions import InvalidTag

from app import config, crypto, storage


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


def _b64e(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _b64d(s: str) -> bytes:
    return base64.b64decode(s.encode("ascii"), validate=True)


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
            pass
        raise


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_account(username: str, password: str) -> bytes:
    if account_exists():
        raise AccountExistsError("an account already exists")
    _check_password_length(password)
    salt = os.urandom(config.SCRYPT_SALT_BYTES)
    db_key = os.urandom(config.DB_KEY_BYTES)
    kek = crypto.derive_kek(password, salt)
    nonce, wrapped = crypto.wrap_key(kek, db_key)
    _save({
        "username": username,
        "bcrypt_hash": crypto.hash_password(password),
        "kdf_salt": _b64e(salt),
        "db_key_nonce": _b64e(nonce),
        "wrapped_db_key": _b64e(wrapped),
        "created_at": _now(),
    })
    conn = storage.connect(db_key)
    storage.init_schema(conn)
    conn.close()
    return db_key


def authenticate(username: str, password: str) -> bytes:
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
            username.encode("utf-8"),
            stored_username.encode("utf-8"),
        )
        password_ok = crypto.verify_password(password, bcrypt_hash)
    except (AttributeError, TypeError, ValueError):
        raise AuthError("bad credentials") from None

    if not (username_ok and password_ok):
        raise AuthError("bad credentials")

    try:
        kek = crypto.derive_kek(password, _b64d(rec["kdf_salt"]))
        db_key = crypto.unwrap_key(
            kek,
            _b64d(rec["db_key_nonce"]),
            _b64d(rec["wrapped_db_key"]),
        )
    except (InvalidTag, KeyError, TypeError, ValueError, binascii.Error):
        raise AuthError("bad credentials") from None
    if len(db_key) != config.DB_KEY_BYTES:
        raise AuthError("bad credentials")
    return db_key


def change_password(old_password: str, new_password: str) -> None:
    if not account_exists():
        raise AuthError("no account")
    _check_password_length(new_password)
    try:
        rec = _load()
        username = rec["username"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        raise AuthError("bad credentials") from None
    db_key = authenticate(username, old_password)  # raises AuthError if wrong
    salt = os.urandom(config.SCRYPT_SALT_BYTES)
    kek = crypto.derive_kek(new_password, salt)
    nonce, wrapped = crypto.wrap_key(kek, db_key)
    rec.update({
        "bcrypt_hash": crypto.hash_password(new_password),
        "kdf_salt": _b64e(salt),
        "db_key_nonce": _b64e(nonce),
        "wrapped_db_key": _b64e(wrapped),
    })
    _save(rec)
