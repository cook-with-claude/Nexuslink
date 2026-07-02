"""Data access for datasets + cdr_records (DATA layer).

Pure SQL over a caller-supplied connection: takes `conn`, returns plain dicts /
scalars, and NEVER commits or rolls back -- the route owns the unit-of-work
(ADR 0001, invariant 2). Imports `infra` only (here: nothing); never audit/api/flask.
"""

from __future__ import annotations


def insert_dataset(conn, name, filename, imported_at, row_count, skipped_count) -> int:
    cur = conn.execute(
        "INSERT INTO datasets (name, filename, imported_at, row_count, skipped_count) "
        "VALUES (?, ?, ?, ?, ?)",
        (name, filename, imported_at, row_count, skipped_count),
    )
    return cur.lastrowid


def bulk_insert_records(conn, dataset_id, rows) -> None:
    conn.executemany(
        "INSERT INTO cdr_records (dataset_id, phone_number, imei, area, timestamp, "
        "call_type, duration_seconds, other_party, other_imei, other_area) "
        "VALUES (:dataset_id, :phone_number, :imei, :area, :timestamp, :call_type, "
        ":duration_seconds, :other_party, :other_imei, :other_area)",
        [dict(r, dataset_id=dataset_id) for r in rows],
    )


def list_datasets(conn) -> list[dict]:
    rows = conn.execute(
        "SELECT id, name, filename, imported_at, row_count, skipped_count "
        "FROM datasets ORDER BY id"
    ).fetchall()
    return [dict(r) for r in rows]


def dataset_exists(conn, dataset_id) -> bool:
    return conn.execute(
        "SELECT 1 FROM datasets WHERE id = ?", (dataset_id,)
    ).fetchone() is not None


def phone_numbers(conn, dataset_id) -> list[dict]:
    rows = conn.execute(
        "SELECT phone_number, COUNT(*) AS count FROM cdr_records "
        "WHERE dataset_id = ? GROUP BY phone_number ORDER BY phone_number",
        (dataset_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def delete_dataset(conn, dataset_id) -> int:
    cur = conn.execute("DELETE FROM datasets WHERE id = ?", (dataset_id,))
    return cur.rowcount


def count_records(conn, dataset_id, phone_number=None) -> int:
    sql = "SELECT COUNT(*) AS n FROM cdr_records WHERE dataset_id = ?"
    params = [dataset_id]
    if phone_number is not None:
        sql += " AND phone_number = ?"
        params.append(phone_number)
    return conn.execute(sql, params).fetchone()["n"]


def read_records_page(conn, dataset_id, offset, limit, phone_number=None) -> list[dict]:
    sql = (
        "SELECT id, phone_number, imei, area, timestamp, call_type, duration_seconds, "
        "other_party, other_imei, other_area FROM cdr_records WHERE dataset_id = ?"
    )
    params = [dataset_id]
    if phone_number is not None:
        sql += " AND phone_number = ?"
        params.append(phone_number)
    sql += " ORDER BY id LIMIT ? OFFSET ?"
    params += [limit, offset]
    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]
