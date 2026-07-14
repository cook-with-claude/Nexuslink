"""Data access for targets (DATA layer).

Pure SQL over a caller-supplied connection; never commits or rolls back (the route
owns the unit-of-work). insert_target may raise sqlcipher3.IntegrityError on the
UNIQUE(dataset_id, phone_number) constraint -- the route catches it and maps 409.
"""

from __future__ import annotations


def dataset_exists(conn, dataset_id) -> bool:
    return conn.execute(
        "SELECT 1 FROM datasets WHERE id = ?", (dataset_id,)
    ).fetchone() is not None


def phone_in_dataset(conn, dataset_id, phone_number) -> bool:
    return conn.execute(
        "SELECT 1 FROM cdr_records WHERE dataset_id = ? AND phone_number = ? LIMIT 1",
        (dataset_id, phone_number),
    ).fetchone() is not None


def duplicate_target(conn, dataset_id, phone_number) -> bool:
    return conn.execute(
        "SELECT 1 FROM targets WHERE dataset_id = ? AND phone_number = ?",
        (dataset_id, phone_number),
    ).fetchone() is not None


def insert_target(conn, name, dataset_id, phone_number, created_at) -> int:
    cur = conn.execute(
        "INSERT INTO targets (name, dataset_id, phone_number, created_at) "
        "VALUES (?, ?, ?, ?)",
        (name, dataset_id, phone_number, created_at),
    )
    return cur.lastrowid


def list_targets(conn) -> list[dict]:
    rows = conn.execute(
        "SELECT id, name, dataset_id, phone_number, created_at FROM targets ORDER BY id"
    ).fetchall()
    return [dict(r) for r in rows]


def delete_target(conn, target_id) -> int:
    cur = conn.execute("DELETE FROM targets WHERE id = ?", (target_id,))
    return cur.rowcount


def rename_target(conn, target_id, name) -> int:
    """Rename a target's label. The UNIQUE constraint is on (dataset_id,
    phone_number), not name, so a label change can never collide. Returns
    rowcount (0 = no such target)."""
    cur = conn.execute(
        "UPDATE targets SET name = ? WHERE id = ?", (name, target_id)
    )
    return cur.rowcount
