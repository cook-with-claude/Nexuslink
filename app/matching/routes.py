"""Contact-matcher blueprint: run a pair comparison, save/list/delete the saved
results that feed the export workbook.

The route owns the unit-of-work; SQL lives in repo.py, the gate engine in
gates.py, orchestration in service.py. POST /match is a pure read (no audit,
matching the frequency explorer); the save/delete endpoints mutate export
staging, so they are audited.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from flask import Blueprint, request

from app.api.guards import current_username, get_db, login_required
from app.api.responses import err, ok
from app.audit import log as audit
from app.matching import repo, service

bp = Blueprint("matching", __name__, url_prefix="/api")


def _pair_from_request(db):
    """(target_a, target_b) from the JSON body, or an error response.

    Same dataset + two distinct targets required (cross-dataset comparison is
    rejected by design for now -- different imports may cover different spans or
    spell areas differently, making "no overlap" misleading)."""
    body = request.get_json(silent=True) or {}
    try:
        a_id = int(body.get("target_a_id"))
        b_id = int(body.get("target_b_id"))
    except (TypeError, ValueError):
        return None, err("BAD_REQUEST", "target_a_id and target_b_id must be integers", 400)
    if a_id == b_id:
        return None, err("BAD_REQUEST", "pick two different targets", 400)
    target_a = repo.get_target(db, a_id)
    target_b = repo.get_target(db, b_id)
    if target_a is None or target_b is None:
        return None, err("NOT_FOUND", "target not found", 404)
    if target_a["dataset_id"] != target_b["dataset_id"]:
        return None, err("BAD_REQUEST", "both targets must belong to the same dataset", 400)
    return (target_a, target_b), None


@bp.post("/match")
@login_required
def match():
    """Run the comparison and return the findings. Stores NOTHING -- results
    enter the export only through the explicit /match/save below."""
    db = get_db()
    pair, error = _pair_from_request(db)
    if error is not None:
        return error
    return ok(service.compute_match(db, *pair))


@bp.post("/match/save")
@login_required
def save_match():
    """Recompute server-side and persist for export (replace-on-same-pair).

    Deliberately does NOT accept a client-supplied result payload: nothing
    client-authored may enter the report. The recompute runs on the same data
    the on-screen run used moments earlier, so stored == shown."""
    db = get_db()
    pair, error = _pair_from_request(db)
    if error is not None:
        return error
    payload = service.compute_match(db, *pair)
    repo.upsert_pair_match(
        db, pair[0]["dataset_id"], pair[0]["id"], pair[1]["id"],
        datetime.now(timezone.utc).isoformat(), json.dumps(payload),
    )
    audit.write_audit(db, current_username(), audit.PAIR_MATCH_SAVE,
                      {"target_a_id": pair[0]["id"], "target_b_id": pair[1]["id"]})
    db.commit()
    return ok(payload)


@bp.get("/match/saved")
@login_required
def saved_matches():
    rows = repo.saved_pair_matches(get_db())
    return ok([{
        "id": r["id"],
        "dataset_id": r["dataset_id"],
        "dataset_name": r["dataset_name"],
        "created_at": r["created_at"],
        "result": json.loads(r["result_json"]),
    } for r in rows])


@bp.delete("/match/saved/<int:match_id>")
@login_required
def delete_saved_match(match_id: int):
    db = get_db()
    if not repo.delete_pair_match(db, match_id):
        return err("NOT_FOUND", "saved match not found", 404)
    audit.write_audit(db, current_username(), audit.PAIR_MATCH_DELETE,
                      {"id": match_id})
    db.commit()
    return ok({"deleted": match_id})
