"""Flask application factory for the Phase 2A backend.

This module is the factory + blueprint registration ONLY. The web-layer helpers
(responses/guards/errors) live in app.api; the system routes in app.api.system
(ADR 0001).
"""

from __future__ import annotations

import os

from flask import Flask, g

from app.api.errors import register_error_handlers


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.urandom(32),          # per-launch; no hardcoded secret
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        # Cap upload size so a huge/malicious .xlsx can't OOM the process; the
        # import pipeline reads the whole file into a DataFrame.
        MAX_CONTENT_LENGTH=50 * 1024 * 1024,  # 50 MiB
        DB_KEY=None,
        USERNAME=None,
    )

    @app.teardown_appcontext
    def _close_db(exc):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    register_error_handlers(app)

    from app.api.system import bp as system_bp
    app.register_blueprint(system_bp)
    from app.auth.routes import bp as auth_bp
    app.register_blueprint(auth_bp)
    from app.datasets.routes import bp as imports_bp
    app.register_blueprint(imports_bp)
    from app.targets import bp as targets_bp
    app.register_blueprint(targets_bp)
    from app.analysis import bp as analysis_bp
    app.register_blueprint(analysis_bp)

    return app
