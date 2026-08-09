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
        # Case-insensitive exact match: the explorer's "exact area" filter should
        # match regardless of capitalization (the records grid's LIKE filter is
        # already ASCII case-insensitive, so typing "hamra" there finds "Hamra").
        # Substring is deliberately NOT used here -- a tally over an exact area
        # must not merge distinct areas like "Hamra" and "Hamburg".
        where.append("area = ? COLLATE NOCASE")
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
    # Interpolated SQL below is built from literals only: every fragment in `where`
    # is a string constant in this function and every caller value is bound as `?`,
    # and `rank_by` is whitelisted against FREQUENCY_FIELDS above (a column name
    # cannot be a bound parameter). Hence the `# nosec B608` markers.
    cond = " AND ".join(where)
    total = conn.execute(
        f"SELECT COUNT(*) AS n FROM cdr_records WHERE {cond}", binds  # nosec B608
    ).fetchone()["n"]
    # NULLs (e.g. other_party on location-only rows) are not a rankable value.
    rows = conn.execute(
        f"SELECT {rank_by} AS value, COUNT(*) AS count FROM cdr_records "  # nosec B608
        f"WHERE {cond} AND {rank_by} IS NOT NULL "
        f"GROUP BY {rank_by} ORDER BY count DESC, value ASC LIMIT ?",
        (*binds, top_n),
    ).fetchall()
    return {"total": total, "top": [dict(r) for r in rows]}


# ---- saved tallies (click-to-save export staging for the frequency explorer) ----

def save_tally(conn, target_id, created_at, filters_json, filter_label,
               tally_json) -> int:
    cur = conn.execute(
        "INSERT INTO saved_tallies "
        "(target_id, created_at, filters_json, filter_label, tally_json) "
        "VALUES (?, ?, ?, ?, ?)",
        (target_id, created_at, filters_json, filter_label, tally_json),
    )
    return cur.lastrowid


def saved_tallies(conn) -> list[dict]:
    rows = conn.execute(
        "SELECT s.id, s.target_id, s.created_at, s.filters_json, s.filter_label, "
        "s.tally_json, t.name AS target_name, t.phone_number, "
        "d.name AS dataset_name "
        "FROM saved_tallies s JOIN targets t ON t.id = s.target_id "
        "JOIN datasets d ON d.id = t.dataset_id ORDER BY s.id",
    ).fetchall()
    return [dict(r) for r in rows]


def delete_tally(conn, tally_id) -> bool:
    cur = conn.execute("DELETE FROM saved_tallies WHERE id = ?", (tally_id,))
    return cur.rowcount > 0


def targets_with_latest_result(conn, target_id=None) -> list[dict]:
    """Every target (or one) with its latest stored result_json (NULL if never analyzed)."""
    # `cond` is one of two string literals (never caller data), so the concatenation
    # below is not an injection vector -- target_id is bound as `?`. Hence `# nosec`.
    cond = "" if target_id is None else "WHERE t.id = ? "
    binds = () if target_id is None else (target_id,)
    rows = conn.execute(
        "SELECT t.id, t.name, t.phone_number, d.name AS dataset_name, r.result_json "  # nosec B608
        "FROM targets t JOIN datasets d ON d.id = t.dataset_id "
        "LEFT JOIN analysis_results r ON r.id = "
        "(SELECT id FROM analysis_results WHERE target_id = t.id ORDER BY id DESC LIMIT 1) "
        + cond + "ORDER BY t.id",
        binds,
    ).fetchall()
    return [dict(r) for r in rows]
