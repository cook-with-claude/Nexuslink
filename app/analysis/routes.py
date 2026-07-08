"""Analysis blueprint: run Phase 1 detection on a target and store the result.

The route owns the unit-of-work; all SQL lives in repo.py, and the Phase 1 detectors
are reached only through bridge.py.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

from flask import Blueprint, Response, request

from app.analysis import bridge, export, repo
from app.api.guards import current_username, get_db, login_required
from app.api.responses import err, ok
from app.audit import log as audit

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


def _opt_int(args, name, lo, hi):
    """Parse an optional bounded int query param; raises ValueError with a
    user-facing message so the route can 400 uniformly."""
    raw = args.get(name)
    if raw is None or raw == "":
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be an integer") from None
    if not (lo <= value <= hi):
        raise ValueError(f"{name} must be between {lo} and {hi}")
    return value


def _opt_date(args, name):
    raw = (args.get(name) or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError:
        raise ValueError(f"{name} must be an ISO date (YYYY-MM-DD)") from None


@bp.get("/targets/<int:target_id>/frequency")
@login_required
def frequency(target_id: int):
    """Filtered frequency explorer: a plain descriptive count over the target's
    filtered records. NOT a detection -- unlike analyze(), the response carries
    no confidence/gates, and filters are legitimate here precisely because a
    tally has no sample-size gate to distort."""
    db = get_db()
    target = repo.get_target(db, target_id)
    if target is None:
        return err("NOT_FOUND", "target not found", 404)

    args = request.args
    rank_by = args.get("rank_by", "area")
    if rank_by not in repo.FREQUENCY_FIELDS:
        return err("BAD_REQUEST",
                   "rank_by must be one of: " + ", ".join(repo.FREQUENCY_FIELDS), 400)
    try:
        call_type = _opt_int(args, "call_type", 1, 22)
        hour_from = _opt_int(args, "hour_from", 0, 23)
        hour_to = _opt_int(args, "hour_to", 0, 23)
        date_from = _opt_date(args, "date_from")
        date_to = _opt_date(args, "date_to")
    except ValueError as e:
        return err("BAD_REQUEST", str(e), 400)
    area = (args.get("area") or "").strip() or None

    result = repo.frequency(
        db, target["dataset_id"], target["phone_number"], rank_by,
        call_type=call_type, area=area, date_from=date_from, date_to=date_to,
        hour_from=hour_from, hour_to=hour_to,
    )
    return ok({
        "target": {"id": target["id"], "name": target["name"],
                   "phone_number": target["phone_number"]},
        "rank_by": rank_by,
        "total_records": result["total"],
        "top": result["top"],
    })


@bp.post("/export/results.xlsx")
@login_required
def export_results():
    """App-wide export of the stored detection answers (all targets by default,
    one target via ?target_id=). It writes an EXPORT audit row (data leaving the
    encrypted store is exactly what the trail exists for), so it is a POST, not a
    GET: a GET is auto-given a HEAD by Flask and is prefetch/reload-idempotent,
    both of which would log phantom exports where no bytes actually left."""
    db = get_db()
    raw = request.args.get("target_id")
    target_id = None
    if raw not in (None, "", "all"):
        try:
            target_id = int(raw)
        except (TypeError, ValueError):
            return err("BAD_REQUEST", "target_id must be an integer or 'all'", 400)
        if repo.get_target(db, target_id) is None:
            return err("NOT_FOUND", "target not found", 404)

    rows = repo.targets_with_latest_result(db, target_id)
    body = export.build_results_workbook(rows)
    audit.write_audit(db, current_username(), audit.EXPORT,
                      {"target_id": target_id, "targets": len(rows)})
    db.commit()
    return Response(body, mimetype=export.XLSX_MIMETYPE, headers={
        "Content-Disposition": 'attachment; filename="nexuslink_results.xlsx"',
    })


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
