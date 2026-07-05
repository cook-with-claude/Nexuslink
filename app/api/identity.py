"""Per-session identity context (SUPPORT layer).

Holds *who* the operator is on THIS request's session, in the signed session
cookie -- today just the username. Phase 3 multi-account (3.2b) adds `user_id`
here. This module is deliberately **data-free**: it never opens or reads the
database. DB-backed identity/role accessors (role + `disabled` resolved from the
`users` row) are an `authz`-tier concern that arrives with multi-account -- a
SUPPORT module reading the DB would invert the layer rule (ADR 0001; ADR 0003).

Keeping identity per-session here (not in process-global `app.config`) is what
lets one server hold more than one unlocked operator at once. `current_username()`
in app.api.guards delegates to this module, so call sites never change (ADR 0001
invariant 6). The DB key stays process-global (the server master key); only
identity de-globalizes.
"""

from __future__ import annotations

from flask import session

_USERNAME_KEY = "username"


def set_identity(username: str) -> None:
    """Bind the current session to `username` (auth routes call this at login/setup)."""
    session[_USERNAME_KEY] = username


def current_username() -> str | None:
    """The username bound to the current request's session, or None."""
    return session.get(_USERNAME_KEY)


def clear_identity() -> None:
    """Remove the identity from this session (logout also calls session.clear())."""
    session.pop(_USERNAME_KEY, None)
