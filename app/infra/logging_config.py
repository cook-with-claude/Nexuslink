"""Operational logging setup (INFRA layer).

Distinct from the *audit* log (`app/audit/log.py`), which is a domain/security trail written
to the encrypted DB. This is developer-facing operational logging: startup, request-level
warnings, and the errors the app deliberately swallows so a user gets a clean response.

Domain/route modules do **not** import this — they just call `logging.getLogger(__name__)`
(stdlib) and log. This module only *configures* the handler/format for the `app` logger tree,
once, from `create_app()`. Level is read from `NEXUSLINK_LOG_LEVEL` (default INFO).

Pure INFRA: imports the stdlib only; no Flask, no domain, no higher layer.
"""

from __future__ import annotations

import logging
import os

_ROOT_LOGGER_NAME = "app"
_DEFAULT_LEVEL = "INFO"
_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def configure_logging() -> logging.Logger:
    """Attach a single stream handler + format to the ``app`` logger tree.

    Idempotent: called once per ``create_app()``, and the test-suite builds many apps, so a
    guard prevents piling up duplicate handlers (which would multiply every log line).
    """
    logger = logging.getLogger(_ROOT_LOGGER_NAME)

    level_name = os.environ.get("NEXUSLINK_LOG_LEVEL", _DEFAULT_LEVEL).upper()
    logger.setLevel(getattr(logging, level_name, logging.INFO))

    # Don't bubble into the root logger's default handler (avoids double lines when a host
    # process — e.g. pytest, or a future server wrapper — also configures the root).
    logger.propagate = False

    if not any(getattr(h, "_nexuslink", False) for h in logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(_FORMAT))
        handler._nexuslink = True  # tag so re-configuration is a no-op  # type: ignore[attr-defined]
        logger.addHandler(handler)

    return logger
