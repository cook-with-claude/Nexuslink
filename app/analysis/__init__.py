"""Analysis domain: run Phase 1 detection on a target and store the result.

routes.py (APPLICATION) owns the request transaction; repo.py (DATA) executes the
analysis_results + record-read SQL and never commits; bridge.py (DOMAIN) is the
seam into the frozen Phase 1 detectors via app.infra.phase1.
"""
