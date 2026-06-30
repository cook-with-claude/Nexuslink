"""Request guards, per-request DB access, and the identity accessor (SUPPORT layer).

current_username() is the single read accessor for the unlocked account's identity.
Phase 3 replaces process-global auth state with a per-session context by swapping
the body of this one function (ADR 0001, invariant 6) rather than every call site.
"""

from __future__ import annotations

import functools

from flask import current_app, g, request, session

from app.api.responses import err
from app.infra import storage


def get_db():
    """A per-request SQLCipher connection opened from the in-memory db_key."""
    if "db" not in g:
        key = current_app.config.get("DB_KEY")
        if key is None:
            raise RuntimeError("no database key in session")
        g.db = storage.connect(key)
    return g.db


def current_username() -> str | None:
    """The currently-unlocked account's username (process-global today; per-session in Phase 3)."""
    return current_app.config["USERNAME"]


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
