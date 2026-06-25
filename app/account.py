"""Single-account lifecycle: setup, authenticate, change-password.

Stores only non-secret material in the auth.json sidecar:
  { username, bcrypt_hash, kdf_salt, db_key_nonce, wrapped_db_key, created_at }
All binary fields are base64-encoded. The raw db_key is returned in-memory to
the caller (the Flask app holds it for the session) but never written to disk.
"""

from __future__ import annotations

import base64
import hmac
import json
import os
from datetime import datetime, timezone

from cryptography.exceptions import InvalidTag

from app import config, crypto, storage


class AccountExistsError(Exception):
    pass


class AuthError(Exception):
    pass


def _b64e(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _b64d(s: str) -> bytes:
    return base64.b64decode(s.encode("ascii"))


def account_exists() -> bool:
    return config.auth_path().exists()


def _load() -> dict:
    with open(config.auth_path(), "r", encoding="utf-8") as fh:
        return json.load(fh)


def _save(record: dict) -> None:
    with open(config.auth_path(), "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2)
        fh.write("\n")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_account(username: str, password: str) -> bytes:
    if account_exists():
        raise AccountExistsError("an account already exists")
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
    rec = _load()
    username_ok = hmac.compare_digest(username, rec["username"])
    password_ok = crypto.verify_password(password, rec["bcrypt_hash"])
    if not (username_ok and password_ok):
        raise AuthError("bad credentials")
    kek = crypto.derive_kek(password, _b64d(rec["kdf_salt"]))
    try:
        return crypto.unwrap_key(kek, _b64d(rec["db_key_nonce"]), _b64d(rec["wrapped_db_key"]))
    except InvalidTag as exc:  # pragma: no cover - defence in depth
        raise AuthError("bad credentials") from exc


def change_password(old_password: str, new_password: str) -> None:
    if not account_exists():
        raise AuthError("no account")
    rec = _load()
    db_key = authenticate(rec["username"], old_password)  # raises AuthError if wrong
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
