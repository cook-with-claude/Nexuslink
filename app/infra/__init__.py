"""Infrastructure layer: filesystem/config, crypto, encrypted storage, and the
single seam to the frozen Phase 1 algorithm.

No domain logic and no Flask live here. Higher layers import infra; infra imports
nothing from the rest of `app`.
"""
