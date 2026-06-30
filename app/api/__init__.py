"""Web layer helpers + system endpoints.

This package deliberately spans two architectural layers (ADR 0001):
  * responses / guards / errors  -> SUPPORT  (low-level, shared by every route)
  * system                       -> APPLICATION (the /api/health + /api/status routes)
"""
