"""Analysis blueprint: run Phase 1 detection on a target and store the result.

The route owns the unit-of-work; all SQL lives in repo.py, and the Phase 1 detectors
are reached only through bridge.py.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

from flask import Blueprint, request

from app.analysis import bridge, repo
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


def _parse_frequency_filters(args):
    """Validated frequency filters from any .get()-able source (query args for
    the live explorer, the JSON body for /frequency/save). Raises ValueError
    with a user-facing message."""
    rank_by = args.get("rank_by") or "area"
    if rank_by not in repo.FREQUENCY_FIELDS:
        raise ValueError("rank_by must be one of: " + ", ".join(repo.FREQUENCY_FIELDS))
    return {
        "rank_by": rank_by,
        "call_type": _opt_int(args, "call_type", 1, 22),
        "hour_from": _opt_int(args, "hour_from", 0, 23),
        "hour_to": _opt_int(args, "hour_to", 0, 23),
        "date_from": _opt_date(args, "date_from"),
        "date_to": _opt_date(args, "date_to"),
        "area": (args.get("area") or "").strip() or None,
    }


def _run_frequency(db, target, filters) -> dict:
    result = repo.frequency(
        db, target["dataset_id"], target["phone_number"], filters["rank_by"],
        call_type=filters["call_type"], area=filters["area"],
        date_from=filters["date_from"], date_to=filters["date_to"],
        hour_from=filters["hour_from"], hour_to=filters["hour_to"],
    )
    return {
        "target": {"id": target["id"], "name": target["name"],
                   "phone_number": target["phone_number"]},
        "rank_by": filters["rank_by"],
        "total_records": result["total"],
        "top": result["top"],
    }


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
    try:
        filters = _parse_frequency_filters(request.args)
    except ValueError as e:
        return err("BAD_REQUEST", str(e), 400)
    return ok(_run_frequency(db, target, filters))


_RANK_LABELS = {"area": "Location / tower", "other_party": "Call partner",
                "call_type": "Call type"}


def _tally_label(target, filters) -> str:
    """The human-readable filter description shown in the export sheet, so a
    saved count is meaningless-proof: the numbers always travel with the exact
    question that produced them."""
    parts = [f"{_RANK_LABELS[filters['rank_by']]} ranking",
             f"target {target['name']} ({target['phone_number']})"]
    if filters["call_type"] is not None:
        parts.append(f"call type {filters['call_type']}")
    if filters["area"]:
        parts.append(f"area {filters['area']}")
    if filters["date_from"] or filters["date_to"]:
        parts.append(f"dates {filters['date_from'] or '…'} → {filters['date_to'] or '…'}")
    if filters["hour_from"] is not None or filters["hour_to"] is not None:
        lo = 0 if filters["hour_from"] is None else filters["hour_from"]
        hi = 23 if filters["hour_to"] is None else filters["hour_to"]
        parts.append(f"hours {lo:02d}:00–{hi:02d}:59")
    return " · ".join(parts)


@bp.post("/frequency/save")
@login_required
def save_tally():
    """Recompute the tally server-side from the submitted filters and persist it
    for export. The client never supplies the stored rows -- nothing
    client-authored may enter the report."""
    db = get_db()
    body = request.get_json(silent=True) or {}
    try:
        target_id = int(body.get("target_id"))
    except (TypeError, ValueError):
        return err("BAD_REQUEST", "target_id must be an integer", 400)
    target = repo.get_target(db, target_id)
    if target is None:
        return err("NOT_FOUND", "target not found", 404)
    try:
        filters = _parse_frequency_filters(body)
    except ValueError as e:
        return err("BAD_REQUEST", str(e), 400)

    payload = _run_frequency(db, target, filters)
    label = _tally_label(target, filters)
    tally_id = repo.save_tally(
        db, target_id, datetime.now(timezone.utc).isoformat(),
        json.dumps(filters), label, json.dumps(payload),
    )
    audit.write_audit(db, current_username(), audit.TALLY_SAVE,
                      {"target_id": target_id, "tally_id": tally_id})
    db.commit()
    return ok({"id": tally_id, "filter_label": label, **payload})


@bp.get("/frequency/saved")
@login_required
def saved_tallies():
    rows = repo.saved_tallies(get_db())
    return ok([{
        "id": r["id"],
        "target_id": r["target_id"],
        "target_name": r["target_name"],
        "phone_number": r["phone_number"],
        "dataset_name": r["dataset_name"],
        "created_at": r["created_at"],
        "filter_label": r["filter_label"],
        "tally": json.loads(r["tally_json"]),
    } for r in rows])


@bp.delete("/frequency/saved/<int:tally_id>")
@login_required
def delete_saved_tally(tally_id: int):
    db = get_db()
    if not repo.delete_tally(db, tally_id):
        return err("NOT_FOUND", "saved count not found", 404)
    audit.write_audit(db, current_username(), audit.TALLY_DELETE, {"id": tally_id})
    db.commit()
    return ok({"deleted": tally_id})


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
