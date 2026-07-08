"""Filesystem locations and crypto tunables for the Phase 2A backend.

No secrets live here. The encrypted DB and the (non-secret) auth.json sidecar
live under APP_DATA_DIR, which defaults to %LOCALAPPDATA%\\NexuslinkCDR on
Windows and ~/.nexuslinkcdr elsewhere, and is overridable via the APP_DATA_DIR
environment variable (tests point it at a temp dir).
"""

from __future__ import annotations

import os
import pathlib

# scrypt parameters for deriving the key-encryption-key from the password.
SCRYPT_N = 2 ** 14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_LEN = 32          # 256-bit KEK
SCRYPT_SALT_BYTES = 16
DB_KEY_BYTES = 32        # 256-bit SQLCipher key
GCM_NONCE_BYTES = 12


def app_data_dir() -> pathlib.Path:
    """Return the app-data directory, creating it if needed."""
    override = os.environ.get("APP_DATA_DIR")
    if override:
        base = pathlib.Path(override)
    elif os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        base = pathlib.Path(os.environ["LOCALAPPDATA"]) / "NexuslinkCDR"
    else:
        base = pathlib.Path.home() / ".nexuslinkcdr"
    base.mkdir(parents=True, exist_ok=True)
    return base


def db_path() -> pathlib.Path:
    return app_data_dir() / "cdr.db"


def auth_path() -> pathlib.Path:
    return app_data_dir() / "auth.json"
