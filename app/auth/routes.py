"""Auth blueprint: setup / login / logout / change-password."""

from __future__ import annotations

from flask import Blueprint, current_app, session

from app.api.guards import current_username, get_db, login_required
from app.api.responses import err, json_body, ok
from app.audit import log as audit
from app.auth import account

bp = Blueprint("auth", __name__, url_prefix="/api")


def _unlock(username: str, db_key: bytes) -> None:
    current_app.config["DB_KEY"] = db_key
    current_app.config["USERNAME"] = username
    session["authenticated"] = True


def _lock() -> None:
    current_app.config["DB_KEY"] = None
    current_app.config["USERNAME"] = None
    session.clear()


def _audit(username: str, event: str, detail=None) -> None:
    """Write an audit row using the currently-unlocked connection."""
    db = get_db()
    audit.write_audit(db, username, event, detail)
    db.commit()


@bp.post("/setup")
def setup():
    body = json_body()
    username, password = body.get("username"), body.get("password")
    if not isinstance(username, str) or not isinstance(password, str) or not username or not password:
        return err("BAD_REQUEST", "username and password required", 400)
    try:
        db_key = account.create_account(username, password)
    except account.AccountExistsError:
        return err("ACCOUNT_EXISTS", "an account already exists", 409)
    except account.PasswordTooLongError as exc:
        return err("BAD_REQUEST", str(exc), 400)
    # Granting the session is this route's unit of work: if the SETUP audit row
    # can't be written, fail closed -- no half-authenticated process/session state
    # behind the 500. (The on-disk account itself stays; login works once the
    # audit trail is writable again.)
    _unlock(username, db_key)
    try:
        _audit(username, audit.SETUP)
    except Exception:
        _lock()
        raise
    return ok({"username": username}, status=201)


@bp.post("/login")
def login():
    body = json_body()
    username, password = body.get("username"), body.get("password")
    if not isinstance(username, str) or not isinstance(password, str) or not username or not password:
        return err("BAD_REQUEST", "username and password required", 400)
    try:
        db_key = account.authenticate(username, password)
    except account.AuthError:
        # The audit_log table lives inside the encrypted DB, which can't be
        # opened without a successful unlock. So a failed login is recorded to a
        # plaintext sidecar instead -- durably, with its real timestamp, and
        # without depending on the attacker ever succeeding (which is exactly the
        # event we most want to keep). See audit.write_failed_login.
        audit.write_failed_login(username)
        return err("UNAUTHENTICATED", "bad credentials", 401)
    # Same fail-closed contract as /setup: an unauditable login grants no session.
    _unlock(username, db_key)
    try:
        _audit(username, audit.LOGIN_SUCCESS)
    except Exception:
        _lock()
        raise
    return ok({"username": username})


@bp.post("/logout")
@login_required
def logout():
    username = current_username()
    try:
        _audit(username, audit.LOGOUT)
    finally:
        # Logout should still revoke local auth state if the audit write fails.
        _lock()
    return ok({})


@bp.post("/change-password")
@login_required
def change_password():
    body = json_body()
    old, new = body.get("old_password"), body.get("new_password")
    if not isinstance(old, str) or not isinstance(new, str) or not old or not new:
        return err("BAD_REQUEST", "old_password and new_password required", 400)
    try:
        account.change_password(old, new)
    except account.PasswordTooLongError as exc:
        return err("BAD_REQUEST", str(exc), 400)
    except account.AuthError:
        return err("UNAUTHENTICATED", "old password incorrect", 401)
    username = current_username()
    _audit(username, audit.CHANGE_PASSWORD)
    return ok({})
