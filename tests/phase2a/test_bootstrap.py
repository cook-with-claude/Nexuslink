"""Increment 3.2b-1: server master-key keyfile bootstrap (app/infra/bootstrap.py)."""
import json
import stat

import pytest

from app.infra import bootstrap, config


def test_first_unlock_creates_keyfile_and_returns_32_byte_key(app_data_dir):
    assert not bootstrap.is_initialized()
    key = bootstrap.unlock("correct horse battery staple")
    assert isinstance(key, bytes) and len(key) == config.DB_KEY_BYTES
    assert bootstrap.is_initialized()
    assert bootstrap.keyfile_path() == config.app_data_dir() / "server.key"


def test_second_unlock_same_passphrase_returns_same_key(app_data_dir):
    first = bootstrap.unlock("pw")
    second = bootstrap.unlock("pw")   # keyfile already exists -> unwrap
    assert first == second


def test_wrong_passphrase_raises_bootstrap_error(app_data_dir):
    bootstrap.unlock("right")
    with pytest.raises(bootstrap.BootstrapError):
        bootstrap.unlock("wrong")


def test_empty_passphrase_raises(app_data_dir):
    with pytest.raises(bootstrap.BootstrapError):
        bootstrap.unlock("")


def test_corrupt_keyfile_raises_bootstrap_error(app_data_dir):
    bootstrap.unlock("pw")
    bootstrap.keyfile_path().write_text("{not json", encoding="utf-8")
    with pytest.raises(bootstrap.BootstrapError):
        bootstrap.unlock("pw")


def test_keyfile_is_json_with_wrapped_fields_only(app_data_dir):
    bootstrap.unlock("pw")
    rec = json.loads(bootstrap.keyfile_path().read_text(encoding="utf-8"))
    assert set(rec) == {"kdf_salt", "nonce", "wrapped_key"}   # no raw key on disk


@pytest.mark.skipif("nt" in __import__("os").name, reason="POSIX perms only")
def test_keyfile_permissions_are_owner_only(app_data_dir):
    bootstrap.unlock("pw")
    mode = stat.S_IMODE(bootstrap.keyfile_path().stat().st_mode)
    assert mode == 0o600
