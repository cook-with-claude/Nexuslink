"""Analysis blueprint: run Phase 1 detection on a target and store the result.

The route owns the unit-of-work; all SQL lives in repo.py, and the Phase 1 detectors
are reached only through bridge.py.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from flask import Blueprint, request

from app.audit import log as audit
from app.api.guards import current_username, get_db, login_required
from app.api.responses import err, ok
from app.analysis import bridge, repo

bp = Blueprint("analysis", __name__, url_prefix="/api")


@bp.post("/targets/<int:target_id>/analyze")
@login_required
def analyze(target_id: int):
    db = get_db()
    target = repo.get_target(db, target_id)
    if target is None:
        return err("NOT_FOUND", "target not found", 404)

    try:
        # Clamp to >= 0: a negative top_n would become a negative list slice
        # (e.g. [:-2] = "all but the last two"), silently returning a wrong ranking.
        top_n = max(0, int(request.args.get("top_n", 5)))
    except (TypeError, ValueError):
        top_n = 5

    rows = repo.read_records(db, target["dataset_id"], target["phone_number"])
    frame = bridge.rows_to_frame(rows)
    result = bridge.analyze_frame(frame, top_n=top_n)
    analyzed_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "target": {"id": target["id"], "name": target["name"],
                   "phone_number": target["phone_number"]},
        "analyzed_at": analyzed_at,
        **result,
    }

    repo.insert_result(db, target_id, analyzed_at, json.dumps(payload))
    audit.write_audit(db, current_username(), audit.ANALYSIS,
                      {"target_id": target_id})
    db.commit()
    return ok(payload)


@bp.get("/targets/<int:target_id>/result")
@login_required
def latest_result(target_id: int):
    db = get_db()
    if repo.get_target(db, target_id) is None:
        return err("NOT_FOUND", "target not found", 404)
    result_json = repo.latest_result(db, target_id)
    if result_json is None:
        return err("NOT_FOUND", "no analysis yet", 404)
    return ok(json.loads(result_json))
