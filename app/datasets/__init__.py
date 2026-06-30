"""Datasets domain: import pipeline + dataset/CDR-record data access.

routes.py (APPLICATION) owns the request transaction; repo.py (DATA) executes the
datasets/cdr_records SQL and never commits; validation.py (DOMAIN) validates rows.
"""
