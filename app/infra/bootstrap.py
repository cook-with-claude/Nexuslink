"""Server master-key bootstrap (INFRA).

The server holds ONE master SQLCipher key for the whole process, unwrapped at
startup from a bootstrap passphrase (ADR 0003 part 2). The wrapped key lives in a
keyfile OUTSIDE the encrypted DB; the raw key exists only in process memory.

Pure INFRA: manages the keyfile and returns the raw key. It does NOT open the
database -- creation stays lazy in api.guards.get_db via the migration seam
(ADR 0002) -- and imports no Flask.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import os
import stat
import tempfile

from cryptography.exceptions import InvalidTag

from app.infra import config, crypto

logger = logging.getLogger(__name__)

KEYFILE_NAME = "server.key"


class BootstrapError(Exception):
    """The master key could not be unwrapped: missing/corrupt keyfile or wrong passphrase."""


def keyfile_path():
    return config.app_data_dir() / KEYFILE_NAME


def is_initialized() -> bool:
    return keyfile_path().exists()


def _b64e(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _b64d(s: str) -> bytes:
    return base64.b64decode(s.encode("ascii"), validate=True)


def _write_keyfile(record: dict) -> None:
    path = keyfile_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(record, fh)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            logger.warning("could not remove temp keyfile %s after a failed write", tmp)
        raise
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # 0600; best-effort (no-op semantics on Windows)
    except OSError:
        logger.warning("could not restrict permissions on %s", path)


def _initialize(passphrase: str) -> bytes:
    master_key = os.urandom(config.DB_KEY_BYTES)
    salt = os.urandom(config.SCRYPT_SALT_BYTES)
    kek = crypto.derive_kek(passphrase, salt)
    nonce, wrapped = crypto.wrap_key(kek, master_key)
    _write_keyfile({"kdf_salt": _b64e(salt), "nonce": _b64e(nonce), "wrapped_key": _b64e(wrapped)})
    return master_key


def _unlock_existing(passphrase: str) -> bytes:
    try:
        with open(keyfile_path(), "r", encoding="utf-8") as fh:
            rec = json.load(fh)
        salt, nonce, wrapped = _b64d(rec["kdf_salt"]), _b64d(rec["nonce"]), _b64d(rec["wrapped_key"])
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError, binascii.Error, AttributeError) as exc:
        raise BootstrapError("corrupt or unreadable keyfile") from exc
    try:
        kek = crypto.derive_kek(passphrase, salt)
        master_key = crypto.unwrap_key(kek, nonce, wrapped)
    except (InvalidTag, ValueError) as exc:
        raise BootstrapError("wrong bootstrap passphrase") from exc
    if len(master_key) != config.DB_KEY_BYTES:
        raise BootstrapError("keyfile holds a malformed key")
    return master_key


def unlock(passphrase: str) -> bytes:
    """Return the raw master key: generate + persist it on first run, else unwrap it.

    Raises BootstrapError on an empty passphrase, a wrong passphrase, or a corrupt keyfile.
    """
    if not passphrase:
        raise BootstrapError("no bootstrap passphrase provided")
    if is_initialized():
        return _unlock_existing(passphrase)
    return _initialize(passphrase)
