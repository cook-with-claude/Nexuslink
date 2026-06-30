"""Analysis blueprint: run Phase 1 detection on a target and store the result."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from flask import Blueprint, request

from app import audit, detection_bridge
from app.api.guards import current_username, get_db, login_required
from app.api.responses import err, ok

bp = Blueprint("analysis", __name__, url_prefix="/api")


def _target(db, target_id: int):
    return db.execute(
        "SELECT id, name, dataset_id, phone_number FROM targets WHERE id = ?",
        (target_id,),
    ).fetchone()


@bp.post("/targets/<int:target_id>/analyze")
@login_required
def analyze(target_id: int):
    db = get_db()
    target = _target(db, target_id)
    if target is None:
        return err("NOT_FOUND", "target not found", 404)

    try:
        # Clamp to >= 0: a negative top_n would become a negative list slice
        # (e.g. [:-2] = "all but the last two"), silently returning a wrong ranking.
        top_n = max(0, int(request.args.get("top_n", 5)))
    except (TypeError, ValueError):
        top_n = 5

    rows = db.execute(
        "SELECT phone_number, imei, area, timestamp, call_type, duration_seconds, "
        "other_party, other_imei, other_area FROM cdr_records "
        "WHERE dataset_id = ? AND phone_number = ?",
        (target["dataset_id"], target["phone_number"]),
    ).fetchall()

    frame = detection_bridge.rows_to_frame([dict(r) for r in rows])
    result = detection_bridge.analyze_frame(frame, top_n=top_n)
    analyzed_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "target": {"id": target["id"], "name": target["name"],
                   "phone_number": target["phone_number"]},
        "analyzed_at": analyzed_at,
        **result,
    }

    db.execute(
        "INSERT INTO analysis_results (target_id, created_at, result_json) VALUES (?, ?, ?)",
        (target_id, analyzed_at, json.dumps(payload)),
    )
    audit.write_audit(db, current_username(), audit.ANALYSIS,
                      {"target_id": target_id})
    db.commit()
    return ok(payload)


@bp.get("/targets/<int:target_id>/result")
@login_required
def latest_result(target_id: int):
    db = get_db()
    if _target(db, target_id) is None:
        return err("NOT_FOUND", "target not found", 404)
    row = db.execute(
        "SELECT result_json FROM analysis_results WHERE target_id = ? "
        "ORDER BY id DESC LIMIT 1",
        (target_id,),
    ).fetchone()
    if row is None:
        return err("NOT_FOUND", "no analysis yet", 404)
    return ok(json.loads(row["result_json"]))
