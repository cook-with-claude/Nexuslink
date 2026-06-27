"""UI blueprint: serves the vanilla SPA shell and its static assets.

This is the ONLY new server surface in Phase 2B. It is purely additive — it
imports nothing from the Phase 2A route logic and is registered from the entry
point (main.py) *after* create_app(), so app/__init__.py and every Phase 2A
module stay byte-untouched.

API-MISMATCH #1: the original brief assumed Flask already served the SPA, but
Phase 2A serves only /api/*. This blueprint closes that gap. It is same-origin
with /api/*, so the SameSite=Strict session cookie and the login_required
JSON/multipart content-type guard both apply unchanged.

Routing note: the SPA uses *hash* routing (#/login, #/dashboard, ...). The
browser never sends the hash to the server, so we only need to serve index.html
at "/" plus the static assets — no Flask catch-all / wildcard route is required.
"""

from __future__ import annotations

import os

from flask import Blueprint, send_from_directory

_WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")

bp = Blueprint("ui", __name__)


@bp.get("/")
def index():
    return send_from_directory(_WEB_DIR, "index.html")


@bp.get("/css/<path:filename>")
def css(filename: str):
    return send_from_directory(os.path.join(_WEB_DIR, "css"), filename)


@bp.get("/js/<path:filename>")
def js(filename: str):
    return send_from_directory(os.path.join(_WEB_DIR, "js"), filename)
