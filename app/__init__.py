"""Flask application factory for the Phase 2A backend."""

from __future__ import annotations

import functools
import os

from flask import Flask, g, jsonify, request, session

from app import account, storage


def ok(data=None, status: int = 200):
    return jsonify({"ok": True, "data": data}), status


def err(code: str, message: str, status: int):
    return jsonify({"ok": False, "error": {"code": code, "message": message}}), status


def get_db():
    """A per-request SQLCipher connection opened from the in-memory db_key."""
    from flask import current_app

    if "db" not in g:
        key = current_app.config.get("DB_KEY")
        if key is None:
            raise RuntimeError("no database key in session")
        g.db = storage.connect(key)
    return g.db


def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        from flask import current_app

        if not session.get("authenticated") or current_app.config.get("DB_KEY") is None:
            return err("UNAUTHENTICATED", "login required", 401)
        # Reject non-JSON bodies on state-changing requests (light CSRF hardening).
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.content_length:
            if not request.is_json and "multipart/form-data" not in (request.content_type or ""):
                return err("BAD_CONTENT_TYPE", "JSON required", 415)
        return view(*args, **kwargs)

    return wrapped


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.urandom(32),          # per-launch; no hardcoded secret
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        DB_KEY=None,
        USERNAME=None,
    )

    @app.teardown_appcontext
    def _close_db(exc):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    @app.get("/api/health")
    def health():
        return ok({"status": "ok"})

    @app.get("/api/status")
    def status():
        return ok({
            "account_exists": account.account_exists(),
            "authenticated": bool(session.get("authenticated")),
        })

    @app.errorhandler(404)
    def _404(e):
        return err("NOT_FOUND", "resource not found", 404)

    @app.errorhandler(405)
    def _405(e):
        return err("METHOD_NOT_ALLOWED", "method not allowed", 405)

    @app.errorhandler(500)
    def _500(e):  # pragma: no cover
        return err("INTERNAL", "internal error", 500)

    # Blueprints registered in later tasks (Tasks 7-12):
    # Uncomment each block as its task lands.
    from app.auth import bp as auth_bp
    app.register_blueprint(auth_bp)
    from app.imports import bp as imports_bp
    app.register_blueprint(imports_bp)
    from app.targets import bp as targets_bp
    app.register_blueprint(targets_bp)
    # from app.analysis import bp as analysis_bp
    # app.register_blueprint(analysis_bp)

    return app
