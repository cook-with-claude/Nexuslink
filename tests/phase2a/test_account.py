import json
import os

import pytest

from app import account, config, storage


def test_setup_creates_account_and_encrypted_db(app_data_dir):
    assert account.account_exists() is False
    db_key = account.create_account("nadim", "hunter2")
    assert account.account_exists() is True
    assert isinstance(db_key, bytes) and len(db_key) == 32
    # The returned key opens the DB and the schema is present.
    conn = storage.connect(db_key)
    names = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "datasets" in names
    conn.close()


def test_second_setup_raises(app_data_dir):
    account.create_account("nadim", "hunter2")
    with pytest.raises(account.AccountExistsError):
        account.create_account("other", "x")


def test_authenticate_returns_same_key(app_data_dir):
    created = account.create_account("nadim", "hunter2")
    got = account.authenticate("nadim", "hunter2")
    assert got == created


def test_authenticate_rejects_bad_password_and_user(app_data_dir):
    account.create_account("nadim", "hunter2")
    with pytest.raises(account.AuthError):
        account.authenticate("nadim", "WRONG")
    with pytest.raises(account.AuthError):
        account.authenticate("someoneelse", "hunter2")


def test_authenticate_rejects_tampered_wrapped_key(app_data_dir):
    account.create_account("nadim", "hunter2")
    auth_path = config.auth_path()
    rec = json.loads(auth_path.read_text(encoding="utf-8"))
    rec["wrapped_db_key"] = rec["wrapped_db_key"][:-2] + "AA"
    auth_path.write_text(json.dumps(rec), encoding="utf-8")

    with pytest.raises(account.AuthError):
        account.authenticate("nadim", "hunter2")


def test_authenticate_rejects_malformed_auth_record(app_data_dir):
    account.create_account("nadim", "hunter2")
    auth_path = config.auth_path()
    rec = json.loads(auth_path.read_text(encoding="utf-8"))
    rec["bcrypt_hash"] = "not-a-bcrypt-hash"
    auth_path.write_text(json.dumps(rec), encoding="utf-8")

    with pytest.raises(account.AuthError):
        account.authenticate("nadim", "hunter2")


def test_change_password_preserves_db_key(app_data_dir):
    original = account.create_account("nadim", "hunter2")
    account.change_password("hunter2", "newpass9")
    with pytest.raises(account.AuthError):
        account.authenticate("nadim", "hunter2")
    assert account.authenticate("nadim", "newpass9") == original


def test_change_password_wrong_old_raises(app_data_dir):
    account.create_account("nadim", "hunter2")
    with pytest.raises(account.AuthError):
        account.change_password("WRONG", "newpass9")


def test_change_password_no_account_raises(app_data_dir):
    with pytest.raises(account.AuthError):
        account.change_password("whatever", "newpass9")


def test_create_account_rejects_overlong_password(app_data_dir):
    with pytest.raises(account.PasswordTooLongError):
        account.create_account("nadim", "x" * 73)
    # The rejection happened before anything was written.
    assert account.account_exists() is False


def test_change_password_rejects_overlong_new_password(app_data_dir):
    account.create_account("nadim", "hunter2")
    with pytest.raises(account.PasswordTooLongError):
        account.change_password("hunter2", "y" * 73)
    # The old password is untouched.
    assert isinstance(account.authenticate("nadim", "hunter2"), bytes)


# ---------------------------------------------------------------------------
# Atomic _save tests
# ---------------------------------------------------------------------------

def test_save_roundtrip_no_temp_files(app_data_dir):
    """_save followed by _load round-trips correctly; no temp files remain."""
    account.create_account("nadim", "hunter2")
    auth_dir = config.auth_path().parent
    files_after = set(os.listdir(auth_dir))
    assert "auth.json" in files_after
    # No leftover .tmp files
    assert not any(f.endswith(".tmp") for f in files_after)
    # Round-trip check via authenticate (which calls _load internally)
    key = account.authenticate("nadim", "hunter2")
    assert isinstance(key, bytes) and len(key) == 32


def test_failed_atomic_write_preserves_original(app_data_dir, monkeypatch):
    """If os.replace raises, the original auth.json is left intact and no temp file remains."""
    account.create_account("nadim", "hunter2")
    auth_path = config.auth_path()
    original_content = auth_path.read_text(encoding="utf-8")
    original_record = json.loads(original_content)

    # Monkeypatch os.replace to simulate a failure during the atomic swap.
    def failing_replace(src, dst):
        raise OSError("simulated os.replace failure")

    monkeypatch.setattr(os, "replace", failing_replace)

    with pytest.raises(OSError, match="simulated os.replace failure"):
        account.change_password("hunter2", "newpass9")

    # Original auth.json must be completely intact.
    restored_content = auth_path.read_text(encoding="utf-8")
    assert json.loads(restored_content) == original_record

    # No temp files left behind.
    auth_dir = auth_path.parent
    assert not any(f.endswith(".tmp") for f in os.listdir(auth_dir))
