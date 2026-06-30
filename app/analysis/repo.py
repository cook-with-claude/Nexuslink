"""Data access for analysis: target lookup, record reads, result rows (DATA layer).

Pure SQL over a caller-supplied connection; returns plain dicts / scalars and never
commits or rolls back -- the route owns the unit-of-work.
"""

from __future__ import annotations


def get_target(conn, target_id) -> dict | None:
    row = conn.execute(
        "SELECT id, name, dataset_id, phone_number FROM targets WHERE id = ?",
        (target_id,),
    ).fetchone()
    return dict(row) if row is not None else None


def read_records(conn, dataset_id, phone_number) -> list[dict]:
    rows = conn.execute(
        "SELECT phone_number, imei, area, timestamp, call_type, duration_seconds, "
        "other_party, other_imei, other_area FROM cdr_records "
        "WHERE dataset_id = ? AND phone_number = ?",
        (dataset_id, phone_number),
    ).fetchall()
    return [dict(r) for r in rows]


def insert_result(conn, target_id, created_at, result_json) -> None:
    conn.execute(
        "INSERT INTO analysis_results (target_id, created_at, result_json) VALUES (?, ?, ?)",
        (target_id, created_at, result_json),
    )


def latest_result(conn, target_id) -> str | None:
    row = conn.execute(
        "SELECT result_json FROM analysis_results WHERE target_id = ? "
        "ORDER BY id DESC LIMIT 1",
        (target_id,),
    ).fetchone()
    return row["result_json"] if row is not None else None
