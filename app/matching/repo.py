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


def area_tallies(conn, dataset_id, phone_number) -> dict[str, int]:
    """area -> how many records the subscriber has there. `area_set` gives only
    the set of areas; the evidence counter needs the per-area VOLUME (how much
    each side actually uses a shared location)."""
    rows = conn.execute(
        "SELECT area, COUNT(*) AS n FROM cdr_records "
        "WHERE dataset_id = ? AND phone_number = ? GROUP BY area",
        (dataset_id, phone_number),
    ).fetchall()
    return {r["area"]: r["n"] for r in rows}


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
