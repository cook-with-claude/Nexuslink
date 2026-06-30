"""HTTP response helpers (SUPPORT layer): JSON envelope + request-body coercion.

Imports flask only; sits a notch below guards/errors, which call err().
"""

from __future__ import annotations

from flask import jsonify, request


def json_body() -> dict:
    """The request JSON, but only when it is an object.

    request.get_json(silent=True) returns whatever the body decodes to, so a
    valid-but-non-object body (a JSON array or scalar) would slip through an
    `or {}` guard and make the subsequent body.get(...) raise AttributeError -> 500.
    Coerce anything that isn't a dict to {} so callers can always .get() safely.
    """
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def ok(data=None, status: int = 200):
    return jsonify({"ok": True, "data": data}), status


def err(code: str, message: str, status: int):
    return jsonify({"ok": False, "error": {"code": code, "message": message}}), status
