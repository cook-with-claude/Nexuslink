from app.infra import config


def test_app_data_dir_uses_env_and_is_created(app_data_dir):
    resolved = config.app_data_dir()
    assert resolved == app_data_dir
    assert resolved.is_dir()


def test_db_and_auth_paths_live_in_app_data_dir(app_data_dir):
    assert config.db_path() == app_data_dir / "cdr.db"
    assert config.auth_path() == app_data_dir / "auth.json"
