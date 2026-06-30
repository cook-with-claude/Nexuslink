"""System endpoints (APPLICATION layer): health probe + first-run/auth status."""

from __future__ import annotations

from flask import Blueprint, session

from app import account
from app.api.responses import ok

bp = Blueprint("system", __name__, url_prefix="/api")


@bp.get("/health")
def health():
    return ok({"status": "ok"})


@bp.get("/status")
def status():
    return ok({
        "account_exists": account.account_exists(),
        "authenticated": bool(session.get("authenticated")),
    })
