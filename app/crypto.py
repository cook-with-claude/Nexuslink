"""Cryptographic primitives for single-account auth and envelope key-wrapping.

Two distinct jobs, two functions:
  * bcrypt  -> the password *verifier* (the requirement names bcrypt).
  * scrypt  -> derives the key-encryption-key (KEK) used to AES-GCM-wrap the
               random 256-bit SQLCipher database key.
The raw database key is never written to disk; only its wrapped form is.
"""

from __future__ import annotations

import bcrypt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from app import config


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def derive_kek(password: str, salt: bytes) -> bytes:
    kdf = Scrypt(
        salt=salt,
        length=config.SCRYPT_LEN,
        n=config.SCRYPT_N,
        r=config.SCRYPT_R,
        p=config.SCRYPT_P,
    )
    return kdf.derive(password.encode("utf-8"))


def wrap_key(kek: bytes, db_key: bytes) -> tuple[bytes, bytes]:
    import os

    nonce = os.urandom(config.GCM_NONCE_BYTES)
    ciphertext = AESGCM(kek).encrypt(nonce, db_key, None)
    return nonce, ciphertext


def unwrap_key(kek: bytes, nonce: bytes, ciphertext: bytes) -> bytes:
    # Raises cryptography.exceptions.InvalidTag if the KEK is wrong.
    return AESGCM(kek).decrypt(nonce, ciphertext, None)
