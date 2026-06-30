"""Targets domain: one target per (dataset_id, phone_number).

routes.py (APPLICATION) owns the request transaction + the IntegrityError->409
mapping; repo.py (DATA) executes the targets SQL and never commits.
"""
