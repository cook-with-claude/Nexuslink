"""Auth blueprint: setup / login / logout / change-password."""

from __future__ import annotations

from flask import Blueprint, current_app, request, session

from app import account, audit, err, get_db, login_required, ok, storage

bp = Blueprint("auth", __name__, url_prefix="/api")


def _unlock(username: str, db_key: bytes) -> None:
    current_app.config["DB_KEY"] = db_key
    current_app.config["USERNAME"] = username
    session["authenticated"] = True


def _audit(username: str, event: str, detail=None) -> None:
    """Write an audit row using the currently-unlocked connection."""
    db = get_db()
    audit.write_audit(db, username, event, detail)
    db.commit()


@bp.post("/setup")
def setup():
    body = request.get_json(silent=True) or {}
    username, password = body.get("username"), body.get("password")
    if not username or not password:
        return err("BAD_REQUEST", "username and password required", 400)
    try:
        db_key = account.create_account(username, password)
    except account.AccountExistsError:
        return err("ACCOUNT_EXISTS", "an account already exists", 409)
    _unlock(username, db_key)
    _audit(username, audit.SETUP)
    return ok({"username": username}, status=201)


@bp.post("/login")
def login():
    body = request.get_json(silent=True) or {}
    username, password = body.get("username"), body.get("password")
    if not username or not password:
        return err("BAD_REQUEST", "username and password required", 400)
    try:
        db_key = account.authenticate(username, password)
    except account.AuthError:
        # Record the failure by unlocking with the stored account is not possible
        # without the password. Buffer it: open the DB only if we can derive the
        # key from a subsequent success. Simplest correct approach: stash failed
        # attempts in app.config and flush them on the next successful login.
        fails = current_app.config.setdefault("PENDING_FAILS", [])
        fails.append({"username": username})
        return err("UNAUTHENTICATED", "bad credentials", 401)
    _unlock(username, db_key)
    for f in current_app.config.pop("PENDING_FAILS", []):
        _audit(f["username"], audit.LOGIN_FAIL, f)
    _audit(username, audit.LOGIN_SUCCESS)
    return ok({"username": username})


@bp.post("/logout")
@login_required
def logout():
    username = current_app.config.get("USERNAME")
    _audit(username, audit.LOGOUT)
    current_app.config["DB_KEY"] = None
    current_app.config["USERNAME"] = None
    session.clear()
    return ok({})


@bp.post("/change-password")
@login_required
def change_password():
    body = request.get_json(silent=True) or {}
    old, new = body.get("old_password"), body.get("new_password")
    if not old or not new:
        return err("BAD_REQUEST", "old_password and new_password required", 400)
    try:
        account.change_password(old, new)
    except account.AuthError:
        return err("UNAUTHENTICATED", "old password incorrect", 401)
    username = current_app.config.get("USERNAME")
    _audit(username, audit.CHANGE_PASSWORD)
    return ok({})
