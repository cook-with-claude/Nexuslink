import os

import pytest
from cryptography.exceptions import InvalidTag

from app.infra import crypto


def test_bcrypt_roundtrip():
    h = crypto.hash_password("hunter2")
    assert h != "hunter2"
    assert crypto.verify_password("hunter2", h) is True
    assert crypto.verify_password("wrong", h) is False


def test_envelope_roundtrip_recovers_db_key():
    salt = os.urandom(16)
    db_key = os.urandom(32)
    kek = crypto.derive_kek("hunter2", salt)
    assert len(kek) == 32
    nonce, ct = crypto.wrap_key(kek, db_key)
    assert len(nonce) == 12
    assert crypto.unwrap_key(kek, nonce, ct) == db_key


def test_wrong_password_cannot_unwrap():
    salt = os.urandom(16)
    db_key = os.urandom(32)
    good = crypto.derive_kek("hunter2", salt)
    bad = crypto.derive_kek("WRONG", salt)
    nonce, ct = crypto.wrap_key(good, db_key)
    with pytest.raises(InvalidTag):
        crypto.unwrap_key(bad, nonce, ct)
