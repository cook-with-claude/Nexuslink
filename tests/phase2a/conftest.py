import os
import pathlib
import pytest


@pytest.fixture()
def app_data_dir(tmp_path, monkeypatch):
    """Point all app-data at an isolated temp dir for every test."""
    d = tmp_path / "appdata"
    monkeypatch.setenv("APP_DATA_DIR", str(d))
    return pathlib.Path(d)
