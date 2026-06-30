"""App-wide error handlers (SUPPORT layer): JSON envelope for 404/405/413/500."""

from __future__ import annotations

from app.api.responses import err


def register_error_handlers(app) -> None:
    @app.errorhandler(404)
    def _404(e):
        return err("NOT_FOUND", "resource not found", 404)

    @app.errorhandler(405)
    def _405(e):
        return err("METHOD_NOT_ALLOWED", "method not allowed", 405)

    @app.errorhandler(413)
    def _413(e):
        return err("PAYLOAD_TOO_LARGE", "uploaded file is too large", 413)

    @app.errorhandler(500)
    def _500(e):  # pragma: no cover
        return err("INTERNAL", "internal error", 500)
