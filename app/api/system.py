"""System endpoints (APPLICATION layer): health probe + first-run/auth status."""

from __future__ import annotations

from flask import Blueprint, current_app, session

from app.api.responses import ok
from app.auth import account

bp = Blueprint("system", __name__, url_prefix="/api")


@bp.get("/health")
def health():
    return ok({"status": "ok"})


@bp.get("/status")
def status():
    return ok({
        "locked": current_app.config.get("DB_KEY") is None,
        "account_exists": account.account_exists(),
        "authenticated": bool(session.get("authenticated")),
    })
