"""Request guards, per-request DB access, and the identity accessor (SUPPORT layer).

current_username() is the single read accessor for the unlocked account's identity.
Phase 3 increment 3.2a swapped its body to read the per-session identity context
(app.api.identity) instead of process-global app.config, without touching any of
the ~7 call sites (ADR 0001, invariant 6). The DB key stays process-global.
"""

from __future__ import annotations

import functools

from flask import current_app, g, request, session

from app.api import identity
from app.api.responses import err
from app.infra import migrations, storage


def get_db():
    """A per-request SQLCipher connection opened from the in-memory db_key.

    The connection is run through the migration seam (ADR 0002) before it is
    cached, so an existing database is auto-upgraded on login. On an up-to-date
    database migrate() is a no-op (one PRAGMA read), so behavior is frozen.
    """
    if "db" not in g:
        key = current_app.config.get("DB_KEY")
        if key is None:
            raise RuntimeError("no database key in session")
        conn = storage.connect(key)
        try:
            migrations.migrate(conn)
        except Exception:
            conn.close()
            raise
        g.db = conn
    return g.db


def current_username() -> str | None:
    """The currently-unlocked account's username, read from the per-session identity
    context (app.api.identity). Callers never change (ADR 0001 invariant 6)."""
    return identity.current_username()


def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("authenticated") or current_app.config.get("DB_KEY") is None:
            return err("UNAUTHENTICATED", "login required", 401)
        # Reject non-JSON bodies on state-changing requests (light CSRF hardening).
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.content_length:
            if not request.is_json and "multipart/form-data" not in (request.content_type or ""):
                return err("BAD_CONTENT_TYPE", "JSON required", 415)
        return view(*args, **kwargs)

    return wrapped
