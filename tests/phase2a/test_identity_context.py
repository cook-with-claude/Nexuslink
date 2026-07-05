"""Increment 3.2a: per-session identity context (app/api/identity.py).

Pins the de-globalization contract: identity lives in THIS session's signed
cookie, not in process-global app.config. Behavior-frozen for the single-account
desktop app (one session), so the rest of the suite is the regression net; these
tests lock the seam itself.
"""

import pytest

from app import create_app


@pytest.fixture()
def client(app_data_dir, bootstrap_key):
    app = create_app()
    app.config.update(TESTING=True, DB_KEY=bootstrap_key)
    c = app.test_client()
    c.post("/api/setup", json={"username": "nadim", "password": "hunter2"})
    return c


def test_identity_module_roundtrip(app_data_dir):
    """set/current/clear round-trips through the session, and is empty by default."""
    from app.api import identity

    app = create_app()
    app.config.update(TESTING=True)
    with app.test_request_context():
        assert identity.current_username() is None
        identity.set_identity("alice")
        assert identity.current_username() == "alice"
        identity.clear_identity()
        assert identity.current_username() is None


def test_login_puts_identity_in_session_not_config(client):
    # De-globalized: no process-global USERNAME slot remains...
    assert "USERNAME" not in client.application.config
    # ...and the identity is carried in THIS client's signed session cookie.
    with client.session_transaction() as sess:
        assert sess.get("username") == "nadim"


def test_logout_clears_session_identity(client):
    client.post("/api/logout")
    with client.session_transaction() as sess:
        assert "username" not in sess
        assert "authenticated" not in sess
