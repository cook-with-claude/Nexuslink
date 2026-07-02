"""Import pipeline (xlsx) + dataset listing/deletion (APPLICATION layer).

The route owns the unit-of-work: it drives validation, calls the repo for data
access, writes the audit row, and commits. All SQL lives in repo.py.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd
from flask import Blueprint, request

from app.api.guards import current_username, get_db, login_required
from app.api.responses import err, ok
from app.audit import log as audit
from app.datasets import repo, validation

logger = logging.getLogger(__name__)

bp = Blueprint("imports", __name__, url_prefix="/api")


@bp.post("/imports")
@login_required
def import_xlsx():
    name = (request.form.get("name") or "").strip()
    if not name:
        return err("BAD_REQUEST", "a dataset name is required", 400)
    upload = request.files.get("file")
    if upload is None or upload.filename == "":
        return err("BAD_REQUEST", "a .xlsx file is required", 400)
    if not upload.filename.lower().endswith(".xlsx"):
        return err("BAD_FILE", "only .xlsx files are supported", 400)

    try:
        df = pd.read_excel(upload, dtype=str, engine="openpyxl")
    except Exception:
        # User sees a clean 400; the real parse error is kept server-side for debugging.
        logger.info("rejected upload %r: not a readable .xlsx", upload.filename, exc_info=True)
        return err("BAD_FILE", "file could not be read as .xlsx", 400)
    finally:
        # Release the spooled-temp-file handle; on Windows it otherwise lingers
        # until GC and can't be deleted while open.
        upload.close()

    missing = validation.missing_columns(list(df.columns))
    if missing:
        return err("SCHEMA_MISMATCH", "missing columns: " + ", ".join(missing), 400)

    clean_rows, skipped_reasons = [], []
    for i, raw in enumerate(df.to_dict(orient="records")):
        clean, reason = validation.validate_row(raw)
        if clean is None:
            skipped_reasons.append({"row": i + 2, "reason": reason})  # +2: header + 1-based
        else:
            clean_rows.append(clean)

    db = get_db()
    dataset_id = repo.insert_dataset(
        db, name, upload.filename, datetime.now(timezone.utc).isoformat(),
        len(clean_rows), len(skipped_reasons),
    )
    repo.bulk_insert_records(db, dataset_id, clean_rows)
    audit.write_audit(db, current_username(), audit.IMPORT,
                      {"dataset_id": dataset_id, "imported": len(clean_rows),
                       "skipped": len(skipped_reasons)})
    db.commit()

    return ok({"dataset_id": dataset_id, "imported": len(clean_rows),
               "skipped": len(skipped_reasons), "skipped_reasons": skipped_reasons}, 201)


@bp.get("/datasets")
@login_required
def list_datasets():
    return ok(repo.list_datasets(get_db()))


@bp.get("/datasets/<int:dataset_id>/phone-numbers")
@login_required
def dataset_phone_numbers(dataset_id: int):
    db = get_db()
    if not repo.dataset_exists(db, dataset_id):
        return err("NOT_FOUND", "dataset not found", 404)
    return ok(repo.phone_numbers(db, dataset_id))


@bp.get("/datasets/<int:dataset_id>/records")
@login_required
def dataset_records(dataset_id: int):
    """Read-only page of the raw imported rows (the Spreadsheet view)."""
    db = get_db()
    if not repo.dataset_exists(db, dataset_id):
        return err("NOT_FOUND", "dataset not found", 404)
    # Bad paging params fall back to defaults rather than 400, matching how
    # analyze() treats a malformed top_n (single local client, read-only view).
    try:
        offset = max(0, int(request.args.get("offset", 0)))
    except (TypeError, ValueError):
        offset = 0
    try:
        limit = min(max(1, int(request.args.get("limit", 100))), 500)
    except (TypeError, ValueError):
        limit = 100
    return ok({
        "total": repo.count_records(db, dataset_id),
        "offset": offset,
        "limit": limit,
        "rows": repo.read_records_page(db, dataset_id, offset, limit),
    })


@bp.delete("/datasets/<int:dataset_id>")
@login_required
def delete_dataset(dataset_id: int):
    db = get_db()
    if repo.delete_dataset(db, dataset_id) == 0:
        return err("NOT_FOUND", "dataset not found", 404)
    # Cascades to cdr_records/targets/analysis_results -- a destructive action
    # that must leave an audit trail like every other state-changing endpoint.
    audit.write_audit(db, current_username(), audit.DATASET_DELETE,
                      {"dataset_id": dataset_id})
    db.commit()
    return ok({})
