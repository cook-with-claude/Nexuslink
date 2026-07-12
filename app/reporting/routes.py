"""Reporting blueprint: the app-wide export endpoint (APPLICATION layer).

Moved from app/analysis/routes.py when the workbook started composing rows from
more than one domain. This module may import several domains' public repo
functions -- app.reporting is the cross-domain composition surface and is
deliberately NOT in the import-linter domain-independence set (the domains
themselves still may not import each other).
"""

from __future__ import annotations

import json

from flask import Blueprint, Response, request

from app.analysis import repo as analysis_repo
from app.api.guards import current_username, get_db, login_required
from app.api.responses import err
from app.audit import log as audit
from app.matching import repo as matching_repo
from app.reporting import export

bp = Blueprint("reporting", __name__, url_prefix="/api")


@bp.post("/export/results.xlsx")
@login_required
def export_results():
    """App-wide export of the stored answers (all targets by default, one target
    via ?target_id=): detections plus the click-to-save staged pair matches and
    explorer counts. It writes an EXPORT audit row (data leaving the encrypted
    store is exactly what the trail exists for), so it is a POST, not a GET: a
    GET is auto-given a HEAD by Flask and is prefetch/reload-idempotent, both of
    which would log phantom exports where no bytes actually left."""
    db = get_db()
    raw = request.args.get("target_id")
    target_id = None
    if raw not in (None, "", "all"):
        try:
            target_id = int(raw)
        except (TypeError, ValueError):
            return err("BAD_REQUEST", "target_id must be an integer or 'all'", 400)
        if analysis_repo.get_target(db, target_id) is None:
            return err("NOT_FOUND", "target not found", 404)

    rows = analysis_repo.targets_with_latest_result(db, target_id)
    pair_matches = [{**r, "result": json.loads(r["result_json"])}
                    for r in matching_repo.saved_pair_matches(db)]
    tallies = [{**r, "tally": json.loads(r["tally_json"])}
               for r in analysis_repo.saved_tallies(db)]
    body = export.build_results_workbook(rows, pair_matches, tallies)
    audit.write_audit(db, current_username(), audit.EXPORT,
                      {"target_id": target_id, "targets": len(rows),
                       "pair_matches": len(pair_matches), "tallies": len(tallies)})
    db.commit()
    return Response(body, mimetype=export.XLSX_MIMETYPE, headers={
        "Content-Disposition": 'attachment; filename="nexuslink_results.xlsx"',
    })
