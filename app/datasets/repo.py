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


def rename_dataset(conn, dataset_id, name) -> int:
    """Rename a dataset's display label. Returns rowcount (0 = no such dataset)."""
    cur = conn.execute(
        "UPDATE datasets SET name = ? WHERE id = ?", (name, dataset_id)
    )
    return cur.rowcount


def _like_pattern(text: str) -> str:
    """Substring match with LIKE wildcards in the user's text made literal."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _records_where(dataset_id, phone_number, call_type, area, other_party):
    """Shared WHERE for the records page and its count, so `total` always
    counts exactly the filtered set the page reads. phone_number/call_type are
    exact (they come from selects); area/other_party are substring matches."""
    sql = " FROM cdr_records WHERE dataset_id = ?"
    params = [dataset_id]
    if phone_number is not None:
        sql += " AND phone_number = ?"
        params.append(phone_number)
    if call_type is not None:
        sql += " AND call_type = ?"
        params.append(call_type)
    if area is not None:
        sql += " AND area LIKE ? ESCAPE '\\'"
        params.append(_like_pattern(area))
    if other_party is not None:
        sql += " AND other_party LIKE ? ESCAPE '\\'"
        params.append(_like_pattern(other_party))
    return sql, params


def count_records(conn, dataset_id, phone_number=None, call_type=None,
                  area=None, other_party=None) -> int:
    where, params = _records_where(dataset_id, phone_number, call_type, area, other_party)
    return conn.execute("SELECT COUNT(*) AS n" + where, params).fetchone()["n"]


# Sortable columns for the records page (whitelist — identifiers can't be
# bound, so only these names ever reach the ORDER BY).
RECORD_SORT_FIELDS = ("timestamp", "duration_seconds")


def read_records_page(conn, dataset_id, offset, limit, phone_number=None,
                      call_type=None, area=None, other_party=None,
                      sort=None, descending=False) -> list[dict]:
    where, params = _records_where(dataset_id, phone_number, call_type, area, other_party)
    if sort is None:
        order = " ORDER BY id"
    else:
        if sort not in RECORD_SORT_FIELDS:
            raise ValueError(f"unsortable column: {sort}")
        # id as tie-break keeps paging stable across equal values.
        order = f" ORDER BY {sort} {'DESC' if descending else 'ASC'}, id"
    sql = (
        "SELECT id, phone_number, imei, area, timestamp, call_type, duration_seconds, "
        "other_party, other_imei, other_area" + where + order + " LIMIT ? OFFSET ?"
    )
    rows = conn.execute(sql, params + [limit, offset]).fetchall()
    return [dict(r) for r in rows]
