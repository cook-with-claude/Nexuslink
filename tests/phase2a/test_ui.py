"""Smoke tests for the Phase 2B UI blueprint (app/ui.py).

The blueprint is registered from the entry point (main.py), not from
create_app(), so these tests register it the same way before exercising it.
They guard the one new server-side surface in Phase 2B: that the SPA shell and
its static assets are actually served, and that registering the blueprint does
not disturb the Phase 2A API.
"""

import pytest

from app import create_app
from app.ui import bp as ui_bp


@pytest.fixture()
def client(app_data_dir):
    app = create_app()
    app.register_blueprint(ui_bp)  # mirror main.py's entry-point registration
    app.config.update(TESTING=True)
    return app.test_client()


def test_serves_spa_shell_at_root(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("Content-Type", "")
    body = r.get_data(as_text=True)
    assert '<div id="app"' in body          # the SPA mount point
    assert "/js/main.js" in body            # entry script is wired up


@pytest.mark.parametrize(
    "path, content_type, needle",
    [
        ("/css/app.css", "text/css", "--accent"),
        ("/js/main.js", "javascript", "startRouter"),
        ("/js/api.js", "javascript", "ApiError"),
        ("/js/store.js", "javascript", "authenticated"),
        # nested path-converter route must resolve screen modules too
        ("/js/screens/results.js", "javascript", "resultsScreen"),
        # contact matcher card + its shared renderer must stay served
        ("/js/screens/spreadsheet.js", "javascript", "matcherCard"),
        ("/js/components.js", "javascript", "matchFindingsBlock"),
    ],
)
def test_serves_static_assets(client, path, content_type, needle):
    r = client.get(path)
    assert r.status_code == 200, path
    assert content_type in r.headers.get("Content-Type", ""), path
    assert needle in r.get_data(as_text=True), path


def test_missing_asset_404s(client):
    assert client.get("/js/does-not-exist.js").status_code == 404


def test_registering_ui_does_not_disturb_api(client):
    # The Phase 2A API envelope and public endpoints still behave unchanged.
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.get_json()["data"]["status"] == "ok"
    r = client.get("/api/status")
    assert r.get_json()["data"]["account_exists"] is False
