"""Data access for the contact matcher (DATA layer).

Fact-gathering SQL over a caller-supplied connection: everything the gate engine
needs to rate a pair, plus CRUD for the saved-pair-match export staging. Pure SQL --
returns plain dicts / scalars, never commits, imports infra only (and not even
that, currently). The gate logic itself lives in gates.py; keep judgment out of
here.
"""

from __future__ import annotations

# Inclusive co-presence pairing window (seconds). 60 minutes, per the matcher
# design spec; gates.py owns the *rating* thresholds, this is the raw pairing rule.
CO_PRESENCE_WINDOW_SECONDS = 3600


def get_target(conn, target_id) -> dict | None:
    row = conn.execute(
        "SELECT id, name, dataset_id, phone_number FROM targets WHERE id = ?",
        (target_id,),
    ).fetchone()
    return dict(row) if row is not None else None


def record_count(conn, dataset_id, phone_number) -> int:
    return conn.execute(
        "SELECT COUNT(*) AS n FROM cdr_records WHERE dataset_id = ? AND phone_number = ?",
        (dataset_id, phone_number),
    ).fetchone()["n"]


def observation_span(conn, dataset_id, phone_number) -> tuple[str, str] | None:
    """(first, last) record timestamp, or None when the target has no records."""
    row = conn.execute(
        "SELECT MIN(timestamp) AS lo, MAX(timestamp) AS hi FROM cdr_records "
        "WHERE dataset_id = ? AND phone_number = ?",
        (dataset_id, phone_number),
    ).fetchone()
    if row["lo"] is None:
        return None
    return (row["lo"], row["hi"])


def contact_tallies(conn, dataset_id, phone_number, exclude=()) -> dict[str, int]:
    """other_party -> record count for one subscriber. `exclude` drops parties that
    must not count as a "contact" here (the pair's own numbers -- talking to each
    other is the direct-contact finding, not a shared third party)."""
    not_in = ""
    binds: list = [dataset_id, phone_number]
    if exclude:
        not_in = f" AND other_party NOT IN ({','.join('?' * len(exclude))})"
        binds.extend(exclude)
    rows = conn.execute(
        "SELECT other_party AS party, COUNT(*) AS n FROM cdr_records "
        "WHERE dataset_id = ? AND phone_number = ? AND other_party IS NOT NULL"
        + not_in + " GROUP BY other_party",
        binds,
    ).fetchall()
    return {r["party"]: r["n"] for r in rows}


def area_set(conn, dataset_id, phone_number) -> set[str]:
    rows = conn.execute(
        "SELECT DISTINCT area FROM cdr_records WHERE dataset_id = ? AND phone_number = ?",
        (dataset_id, phone_number),
    ).fetchall()
    return {r["area"] for r in rows}


def direct_contact(conn, dataset_id, phone_a, phone_b) -> dict:
    """Interactions between the two subscribers themselves, from either side's rows.

    call_type codes (Phase 1 source of truth): 1=out call, 2=in call, 11=out SMS,
    22=in SMS. "a_to_b" = records that describe A-originated traffic: A's own
    outgoing rows plus B's incoming rows (a dataset may carry one side or both).
    """
    rows = conn.execute(
        "SELECT phone_number, call_type, timestamp FROM cdr_records "
        "WHERE dataset_id = ? AND ((phone_number = ? AND other_party = ?) "
        "OR (phone_number = ? AND other_party = ?)) ORDER BY timestamp",
        (dataset_id, phone_a, phone_b, phone_b, phone_a),
    ).fetchall()
    out = {"total": len(rows), "calls": 0, "sms": 0, "a_to_b": 0, "b_to_a": 0,
           "first": None, "last": None}
    for r in rows:
        if r["call_type"] in (1, 2):
            out["calls"] += 1
        elif r["call_type"] in (11, 22):
            out["sms"] += 1
        a_originated = (r["phone_number"] == phone_a and r["call_type"] in (1, 11)) or \
                       (r["phone_number"] == phone_b and r["call_type"] in (2, 22))
        out["a_to_b" if a_originated else "b_to_a"] += 1
    if rows:
        out["first"], out["last"] = rows[0]["timestamp"], rows[-1]["timestamp"]
    return out


def co_presence_events(conn, dataset_id, phone_a, phone_b) -> list[dict]:
    """Meet-up events: both subscribers have a record in the same area within
    CO_PRESENCE_WINDOW_SECONDS (inclusive). All pairings in the same (area, day)
    collapse into ONE event -- a long call session must not inflate the count.
    The day is taken from subscriber A's record (deterministic across runs)."""
    rows = conn.execute(
        "SELECT a.area AS area, substr(a.timestamp, 1, 10) AS day, "
        "MIN(a.timestamp) AS a_time, MIN(b.timestamp) AS b_time "
        "FROM cdr_records a JOIN cdr_records b "
        "ON b.dataset_id = a.dataset_id AND b.area = a.area "
        "AND b.phone_number = ? "
        "AND abs(strftime('%s', a.timestamp) - strftime('%s', b.timestamp)) <= ? "
        "WHERE a.dataset_id = ? AND a.phone_number = ? "
        "GROUP BY a.area, substr(a.timestamp, 1, 10) "
        "ORDER BY day, a.area",
        (phone_b, CO_PRESENCE_WINDOW_SECONDS, dataset_id, phone_a),
    ).fetchall()
    return [dict(r) for r in rows]


def direct_contact_records(conn, dataset_id, phone_a, phone_b) -> list[dict]:
    """The raw records BETWEEN the pair (either side's rows), for the ledger.
    `direct_contact` above aggregates the same records into counts."""
    rows = conn.execute(
        "SELECT phone_number, timestamp, call_type, duration_seconds, other_party, area "
        "FROM cdr_records WHERE dataset_id = ? "
        "AND ((phone_number = ? AND other_party = ?) OR (phone_number = ? AND other_party = ?)) "
        "ORDER BY timestamp",
        (dataset_id, phone_a, phone_b, phone_b, phone_a),
    ).fetchall()
    return [dict(r) for r in rows]


def records_for(conn, dataset_id, phones, parties=None, areas=None) -> list[dict]:
    """Raw CDR records for the given subscriber(s), optionally restricted to a set
    of counterparties or a set of areas. Feeds the pair record ledger, which lists
    the actual calls rather than summarizing them.

    `parties` / `areas` are caller-supplied lists (never user input verbatim -- the
    ledger derives them from the pair's own shared sets), bound as parameters.
    """
    if not phones or (parties is not None and not parties) or (areas is not None and not areas):
        return []
    sql = ("SELECT phone_number, timestamp, call_type, duration_seconds, other_party, area "
           "FROM cdr_records WHERE dataset_id = ? "
           f"AND phone_number IN ({','.join('?' * len(phones))})")
    binds: list = [dataset_id, *phones]
    if parties is not None:
        sql += f" AND other_party IN ({','.join('?' * len(parties))})"
        binds.extend(parties)
    if areas is not None:
        sql += f" AND area IN ({','.join('?' * len(areas))})"
        binds.extend(areas)
    sql += " ORDER BY timestamp, phone_number"
    return [dict(r) for r in conn.execute(sql, binds).fetchall()]


def targets_by_phone(conn, dataset_id) -> dict[str, dict]:
    """phone_number -> target row, for every target of this dataset. The ledger
    names parties by their target name where one exists, and flags a shared contact
    who is THEMSELVES a target (someone else under investigation)."""
    rows = conn.execute(
        "SELECT id, name, phone_number FROM targets WHERE dataset_id = ?",
        (dataset_id,),
    ).fetchall()
    return {r["phone_number"]: dict(r) for r in rows}


def other_user_count(conn, dataset_id, phone_a, phone_b) -> int:
    """Distinct subscribers in the dataset besides the pair (distinctiveness base)."""
    return conn.execute(
        "SELECT COUNT(DISTINCT phone_number) AS n FROM cdr_records "
        "WHERE dataset_id = ? AND phone_number NOT IN (?, ?)",
        (dataset_id, phone_a, phone_b),
    ).fetchone()["n"]


_CONTACT_SPREAD = (
    "SELECT COUNT(DISTINCT phone_number) AS k FROM cdr_records "
    "WHERE dataset_id = ? AND other_party IS NOT NULL GROUP BY other_party"
)
# The rarity base considers SHARED contacts only (k >= 2): most contacts in any
# dataset are personal (k = 1), so a median over everything would always be 1
# and nothing shared could ever count as rare.
_SHARED_SPREAD = _CONTACT_SPREAD + " HAVING COUNT(DISTINCT phone_number) >= 2"


def dataset_interconnectedness(conn, dataset_id) -> dict:
    """Dataset-level facts for the adaptive mode (spec 2026-07-13).

    dataset_density: average shared contacts per subscriber pair = sum over
    contacts of C(k, 2) / C(n, 2), where k = subscribers contacting that party.
    One GROUP BY, no O(n^2) pass. contact_spread_median: the typical SHARED
    contact's k (the close-knit rarity base)."""
    n = conn.execute(
        "SELECT COUNT(DISTINCT phone_number) AS n FROM cdr_records WHERE dataset_id = ?",
        (dataset_id,),
    ).fetchone()["n"]
    agg = conn.execute(
        f"SELECT COUNT(*) AS parties, COALESCE(SUM(k * (k - 1) / 2), 0) AS overlap "
        f"FROM ({_SHARED_SPREAD})",
        (dataset_id,),
    ).fetchone()
    pairs = n * (n - 1) // 2
    median = 2  # no shared contacts at all -> mode is strangers, base unused
    if agg["parties"]:
        median = conn.execute(
            f"SELECT k FROM ({_SHARED_SPREAD}) ORDER BY k LIMIT 1 OFFSET ?",
            (dataset_id, (agg["parties"] - 1) // 2),
        ).fetchone()["k"]
    return {
        "dataset_density": (agg["overlap"] / pairs) if pairs else 0.0,
        "contact_spread_median": median,
    }


def _commonality(conn, dataset_id, column, values, phone_a, phone_b) -> dict[str, int]:
    if not values:
        return {}
    marks = ",".join("?" * len(values))
    rows = conn.execute(
        f"SELECT {column} AS value, COUNT(DISTINCT phone_number) AS users "
        f"FROM cdr_records WHERE dataset_id = ? AND {column} IN ({marks}) "
        "AND phone_number NOT IN (?, ?) "
        f"GROUP BY {column}",
        (dataset_id, *values, phone_a, phone_b),
    ).fetchall()
    counts = {r["value"]: r["users"] for r in rows}
    return {v: counts.get(v, 0) for v in values}


def contact_commonality(conn, dataset_id, parties, phone_a, phone_b) -> dict[str, int]:
    """party -> how many OTHER subscribers also have it as a contact. `column` is a
    fixed identifier supplied by this module, never user input."""
    return _commonality(conn, dataset_id, "other_party", list(parties), phone_a, phone_b)


def area_commonality(conn, dataset_id, areas, phone_a, phone_b) -> dict[str, int]:
    """area -> how many OTHER subscribers also have records there."""
    return _commonality(conn, dataset_id, "area", list(areas), phone_a, phone_b)


# ---- saved pair matches (click-to-save export staging) ----

def upsert_pair_match(conn, dataset_id, target_a_id, target_b_id, created_at,
                      result_json) -> None:
    """Save (or replace) the pair's stored result. Pair identity is
    order-normalized so A<->B and B<->A occupy the same UNIQUE slot."""
    lo, hi = sorted((target_a_id, target_b_id))
    conn.execute(
        "INSERT INTO saved_pair_matches "
        "(dataset_id, target_a_id, target_b_id, created_at, result_json) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(target_a_id, target_b_id) "
        "DO UPDATE SET created_at = excluded.created_at, "
        "result_json = excluded.result_json",
        (dataset_id, lo, hi, created_at, result_json),
    )


def saved_pair_matches(conn) -> list[dict]:
    rows = conn.execute(
        "SELECT m.id, m.dataset_id, m.created_at, m.result_json, "
        "d.name AS dataset_name "
        "FROM saved_pair_matches m JOIN datasets d ON d.id = m.dataset_id "
        "ORDER BY m.id",
    ).fetchall()
    return [dict(r) for r in rows]


def delete_pair_match(conn, match_id) -> bool:
    cur = conn.execute("DELETE FROM saved_pair_matches WHERE id = ?", (match_id,))
    return cur.rowcount > 0


# ---- saved pair-record ledgers (click-to-save export staging) ----
# Ledgers ACCUMULATE (no UNIQUE on the pair, unlike saved_pair_matches): a ledger
# is a record listing, so saving the same pair twice is a legitimate act.

def save_ledger(conn, dataset_id, target_a_id, target_b_id, created_at,
                row_count, rows_json) -> int:
    cur = conn.execute(
        "INSERT INTO saved_ledgers "
        "(dataset_id, target_a_id, target_b_id, created_at, row_count, rows_json) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (dataset_id, target_a_id, target_b_id, created_at, row_count, rows_json),
    )
    return cur.lastrowid


def saved_ledgers(conn) -> list[dict]:
    rows = conn.execute(
        "SELECT l.id, l.dataset_id, l.created_at, l.row_count, l.rows_json, "
        "d.name AS dataset_name, "
        "ta.name AS name_a, ta.phone_number AS phone_a, "
        "tb.name AS name_b, tb.phone_number AS phone_b "
        "FROM saved_ledgers l "
        "JOIN datasets d ON d.id = l.dataset_id "
        "JOIN targets ta ON ta.id = l.target_a_id "
        "JOIN targets tb ON tb.id = l.target_b_id "
        "ORDER BY l.id",
    ).fetchall()
    return [dict(r) for r in rows]


def delete_ledger(conn, ledger_id) -> bool:
    cur = conn.execute("DELETE FROM saved_ledgers WHERE id = ?", (ledger_id,))
    return cur.rowcount > 0
