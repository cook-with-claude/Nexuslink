"""Targets blueprint: one target per (dataset_id, phone_number) (APPLICATION layer).

The route owns the unit-of-work and the IntegrityError->409 mapping; all SQL
lives in repo.py.
"""

from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint
from sqlcipher3 import dbapi2 as sqlcipher

from app.api.guards import current_username, get_db, login_required
from app.api.responses import err, json_body, ok
from app.audit import log as audit
from app.targets import repo

bp = Blueprint("targets", __name__, url_prefix="/api")


@bp.post("/targets")
@login_required
def create_target():
    body = json_body()
    name = body.get("name")
    dataset_id = body.get("dataset_id")
    phone_number = body.get("phone_number")
    # Validate TYPES before any DB call. dataset_id and phone_number are bound
    # straight into SQL below; a JSON object/array (or other non-bindable type)
    # would otherwise raise sqlcipher3.InterfaceError -> 500. dataset_id must be a
    # real int (bool is an int subclass -> reject explicitly); phone_number a
    # non-empty string (the column is TEXT and the dataset lookup is an exact match).
    if (
        not isinstance(name, str) or not name.strip()
        or not isinstance(dataset_id, int) or isinstance(dataset_id, bool)
        or not isinstance(phone_number, str) or not phone_number
    ):
        return err("BAD_REQUEST", "name, dataset_id, phone_number required", 400)
    name = name.strip()

    db = get_db()
    if not repo.dataset_exists(db, dataset_id):
        return err("NOT_FOUND", "dataset not found", 404)
    if not repo.phone_in_dataset(db, dataset_id, phone_number):
        return err("NOT_FOUND", "phone_number not in dataset", 404)
    if repo.duplicate_target(db, dataset_id, phone_number):
        return err("CONFLICT", "a target already exists for this phone in this dataset", 409)

    created_at = datetime.now(timezone.utc).isoformat()
    try:
        tid = repo.insert_target(db, name, dataset_id, phone_number, created_at)
    except sqlcipher.IntegrityError as exc:
        db.rollback()
        if "UNIQUE constraint failed" in str(exc) and "targets" in str(exc):
            return err(
                "CONFLICT",
                "a target already exists for this phone in this dataset",
                409,
            )
        raise
    audit.write_audit(db, current_username(), audit.TARGET_CREATE,
                      {"target_id": tid, "dataset_id": dataset_id})
    db.commit()
    return ok({"id": tid, "name": name, "dataset_id": dataset_id,
               "phone_number": phone_number}, 201)


@bp.get("/targets")
@login_required
def list_targets():
    return ok(repo.list_targets(get_db()))


@bp.delete("/targets/<int:target_id>")
@login_required
def delete_target(target_id: int):
    db = get_db()
    if repo.delete_target(db, target_id) == 0:
        return err("NOT_FOUND", "target not found", 404)
    audit.write_audit(db, current_username(), audit.TARGET_DELETE,
                      {"target_id": target_id})
    db.commit()
    return ok({})
