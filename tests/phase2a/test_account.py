import pytest
from app import account, storage


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
