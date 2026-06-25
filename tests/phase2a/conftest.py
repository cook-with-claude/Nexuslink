import pathlib
import pytest


@pytest.fixture()
def app_data_dir(tmp_path, monkeypatch):
    """Point all app-data at an isolated temp dir for every test."""
    d = tmp_path / "appdata"
    monkeypatch.setenv("APP_DATA_DIR", str(d))
    return pathlib.Path(d)


import pandas as pd


@pytest.fixture()
def sample_xlsx(tmp_path):
    """Convert Phase 1's existing synthetic sample_data.csv (users A-E) to .xlsx.

    Reuses real Phase 1 fixture data - no invented rows. If the CSV is missing,
    regenerate it deterministically via Phase 1's dev_fixtures.
    """
    import subprocess
    import sys

    here = pathlib.Path(__file__).resolve().parents[2]
    csv = here / "phase1_cdr" / "sample_data.csv"
    if not csv.exists():
        subprocess.run([sys.executable, str(here / "phase1_cdr" / "dev_fixtures.py")],
                       check=True, cwd=str(here / "phase1_cdr"))
    df = pd.read_csv(csv, dtype={"phone_number": str, "imei": str,
                                 "other_party": str, "other_imei": str})
    out = tmp_path / "sample.xlsx"
    df.to_excel(out, index=False, engine="openpyxl")
    return out
