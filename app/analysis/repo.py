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


# Columns the frequency explorer may rank by. Identifiers cannot be bound as SQL
# parameters, so rank_by goes through this whitelist -- never user input.
FREQUENCY_FIELDS = ("area", "other_party", "call_type")


def frequency(conn, dataset_id, phone_number, rank_by, *, call_type=None, area=None,
              date_from=None, date_to=None, hour_from=None, hour_to=None,
              top_n=5) -> dict:
    """Descriptive tally over a filtered slice of one target's records.

    Returns the filtered record count plus the top_n most frequent values of
    `rank_by`. Deliberately NOT a detection: no gates, no confidence -- the
    caller must not present this as an inference.
    """
    if rank_by not in FREQUENCY_FIELDS:
        raise ValueError(f"rank_by must be one of {FREQUENCY_FIELDS}")
    where = ["dataset_id = ?", "phone_number = ?"]
    binds: list = [dataset_id, phone_number]
    if call_type is not None:
        where.append("call_type = ?")
        binds.append(call_type)
    if area is not None:
        where.append("area = ?")
        binds.append(area)
    # Timestamps are stored as naive ISO-8601 ("YYYY-MM-DDTHH:MM:SS"), so the
    # date is a prefix substring and the hour sits at chars 12-13.
    if date_from is not None:
        where.append("substr(timestamp, 1, 10) >= ?")
        binds.append(date_from)
    if date_to is not None:
        where.append("substr(timestamp, 1, 10) <= ?")
        binds.append(date_to)
    if hour_from is not None or hour_to is not None:
        lo = 0 if hour_from is None else hour_from
        hi = 23 if hour_to is None else hour_to
        hour = "CAST(substr(timestamp, 12, 2) AS INTEGER)"
        if lo <= hi:
            where.append(f"{hour} BETWEEN ? AND ?")
        else:  # overnight window, e.g. 22-06
            where.append(f"({hour} >= ? OR {hour} <= ?)")
        binds.extend([lo, hi])
    cond = " AND ".join(where)
    total = conn.execute(
        f"SELECT COUNT(*) AS n FROM cdr_records WHERE {cond}", binds
    ).fetchone()["n"]
    # NULLs (e.g. other_party on location-only rows) are not a rankable value.
    rows = conn.execute(
        f"SELECT {rank_by} AS value, COUNT(*) AS count FROM cdr_records "
        f"WHERE {cond} AND {rank_by} IS NOT NULL "
        f"GROUP BY {rank_by} ORDER BY count DESC, value ASC LIMIT ?",
        (*binds, top_n),
    ).fetchall()
    return {"total": total, "top": [dict(r) for r in rows]}


def targets_with_latest_result(conn, target_id=None) -> list[dict]:
    """Every target (or one) with its latest stored result_json (NULL if never analyzed)."""
    cond = "" if target_id is None else "WHERE t.id = ? "
    binds = () if target_id is None else (target_id,)
    rows = conn.execute(
        "SELECT t.id, t.name, t.phone_number, d.name AS dataset_name, r.result_json "
        "FROM targets t JOIN datasets d ON d.id = t.dataset_id "
        "LEFT JOIN analysis_results r ON r.id = "
        "(SELECT id FROM analysis_results WHERE target_id = t.id ORDER BY id DESC LIMIT 1) "
        + cond + "ORDER BY t.id",
        binds,
    ).fetchall()
    return [dict(r) for r in rows]
