"""Targets blueprint: one target per (dataset_id, phone_number)."""

from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, current_app
from sqlcipher3 import dbapi2 as sqlcipher

from app import audit, err, get_db, json_body, login_required, ok

bp = Blueprint("targets", __name__, url_prefix="/api")


@bp.post("/targets")
@login_required
def create_target():
    body = json_body()
    name = body.get("name")
    dataset_id = body.get("dataset_id")
    phone_number = body.get("phone_number")
    if not isinstance(name, str) or not name.strip() or dataset_id is None or not phone_number:
        return err("BAD_REQUEST", "name, dataset_id, phone_number required", 400)
    name = name.strip()

    db = get_db()
    if db.execute("SELECT 1 FROM datasets WHERE id = ?", (dataset_id,)).fetchone() is None:
        return err("NOT_FOUND", "dataset not found", 404)
    present = db.execute(
        "SELECT 1 FROM cdr_records WHERE dataset_id = ? AND phone_number = ? LIMIT 1",
        (dataset_id, phone_number),
    ).fetchone()
    if present is None:
        return err("NOT_FOUND", "phone_number not in dataset", 404)
    dup = db.execute(
        "SELECT 1 FROM targets WHERE dataset_id = ? AND phone_number = ?",
        (dataset_id, phone_number),
    ).fetchone()
    if dup is not None:
        return err("CONFLICT", "a target already exists for this phone in this dataset", 409)

    created_at = datetime.now(timezone.utc).isoformat()
    try:
        cur = db.execute(
            "INSERT INTO targets (name, dataset_id, phone_number, created_at) "
            "VALUES (?, ?, ?, ?)",
            (name, dataset_id, phone_number, created_at),
        )
    except sqlcipher.IntegrityError as exc:
        db.rollback()
        if "UNIQUE constraint failed" in str(exc) and "targets" in str(exc):
            return err(
                "CONFLICT",
                "a target already exists for this phone in this dataset",
                409,
            )
        raise
    tid = cur.lastrowid
    audit.write_audit(db, current_app.config["USERNAME"], audit.TARGET_CREATE,
                      {"target_id": tid, "dataset_id": dataset_id})
    db.commit()
    return ok({"id": tid, "name": name, "dataset_id": dataset_id,
               "phone_number": phone_number}, 201)


@bp.get("/targets")
@login_required
def list_targets():
    db = get_db()
    rows = db.execute(
        "SELECT id, name, dataset_id, phone_number, created_at FROM targets ORDER BY id"
    ).fetchall()
    return ok([dict(r) for r in rows])


@bp.delete("/targets/<int:target_id>")
@login_required
def delete_target(target_id: int):
    db = get_db()
    cur = db.execute("DELETE FROM targets WHERE id = ?", (target_id,))
    if cur.rowcount == 0:
        return err("NOT_FOUND", "target not found", 404)
    audit.write_audit(db, current_app.config["USERNAME"], audit.TARGET_DELETE,
                      {"target_id": target_id})
    db.commit()
    return ok({})
