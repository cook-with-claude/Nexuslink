"""Pair record ledger: the ACTUAL records behind a pair, not a verdict about them.

Spec: docs/superpowers/specs/2026-07-13-pair-record-ledger-design.md

Its own feature (own endpoints, own card, own export sheet) but deliberately inside
the matching domain: it needs the same shared-contact / co-presence facts AND the
same distinctive/common classification the verdicts use (gates.classify_shared_
contacts), so their labels can never disagree. A separate package would have to
either import this domain (breaking the independence contract) or re-implement the
SQL and drift.

Four categories, every matching record listed individually:
  direct            records between the pair themselves
  shared_contact    records from EITHER side to a contact they both have
  meet_up_location  records in a shared area where a co-presence event happened
  shared_location   records in a shared area with NO co-presence (same place,
                    different times -- a real signal the verdicts only mention
                    in passing)

Common contacts/areas ARE listed, clearly labeled -- never silently dropped (the
analyst must be able to audit what the matcher discounted) and never called
evidence. Nothing here is gated: no strengths, no confidence.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.matching import gates, repo

CATEGORY_LABELS = {
    "direct": "Direct contact",
    "shared_contact": "Shared contact",
    "meet_up_location": "Meet-up location",
    "shared_location": "Shared location",
}


def _row(record, category, targets, distinctive=None):
    """One ledger row. Parties are named by their TARGET name wherever the dataset
    has a target for the number: on a direct row both sides are targets, and a
    shared contact who is themselves a target is flagged -- that is someone else
    under investigation, which an analyst must not have to notice by eye."""
    who = targets.get(record["phone_number"])
    party = record["other_party"]
    party_target = targets.get(party) if party else None
    return {
        "category": category,
        "category_label": CATEGORY_LABELS[category],
        "who": who["name"] if who else record["phone_number"],
        "who_phone": record["phone_number"],
        "timestamp": record["timestamp"],
        "call_type": record["call_type"],
        "duration_seconds": record["duration_seconds"],
        "other_party": party,
        "other_party_name": party_target["name"] if party_target else None,
        "other_party_is_target": party_target is not None,
        "area": record["area"],
        "distinctive": distinctive,
    }


def compute_ledger(conn, target_a: dict, target_b: dict) -> dict:
    """Every record linking the two targets, ordered by time within each category.

    Callers validate the targets exist / same dataset / are distinct. The pair is
    canonicalized (as compute_match does) so A-vs-B and B-vs-A are identical.
    """
    if target_b["phone_number"] < target_a["phone_number"]:
        target_a, target_b = target_b, target_a
    dataset_id = target_a["dataset_id"]
    phone_a, phone_b = target_a["phone_number"], target_b["phone_number"]
    both = [phone_a, phone_b]

    targets = repo.targets_by_phone(conn, dataset_id)

    # Same facts the verdicts are built from -- one source, so the ledger's labels
    # and the matcher's ratings can never disagree.
    contacts_a = repo.contact_tallies(conn, dataset_id, phone_a, exclude=(phone_a, phone_b))
    contacts_b = repo.contact_tallies(conn, dataset_id, phone_b, exclude=(phone_a, phone_b))
    shared_parties = sorted(set(contacts_a) & set(contacts_b))
    areas_a = repo.area_set(conn, dataset_id, phone_a)
    areas_b = repo.area_set(conn, dataset_id, phone_b)
    shared_areas = areas_a & areas_b
    co_events = repo.co_presence_events(
        conn, dataset_id, phone_a, phone_b,
        gates.CO_PRESENCE_WINDOW_SECONDS, gates.SESSION_GAP_SECONDS)
    meet_up_areas = sorted({e["area"] for e in co_events} & shared_areas)
    shared_only_areas = sorted(shared_areas - set(meet_up_areas))

    other_users = repo.other_user_count(conn, dataset_id, phone_a, phone_b)
    mode_facts = repo.dataset_interconnectedness(
        conn, dataset_id, gates.HUB_UBIQUITY_FRACTION)
    mode = gates.classify_dataset(mode_facts["dataset_density"])["mode"]
    distinctive_parties = set(gates.classify_shared_contacts(
        shared_parties,
        repo.contact_commonality(conn, dataset_id, shared_parties, phone_a, phone_b),
        other_users, mode, mode_facts["contact_spread_median"]))
    all_shared_areas = meet_up_areas + shared_only_areas
    distinctive_areas = set(gates.classify_areas(
        all_shared_areas,
        repo.area_commonality(conn, dataset_id, all_shared_areas, phone_a, phone_b),
        other_users))

    rows: list[dict] = []
    seen_record_ids: set[int] = set()

    def append_once(record, category, distinctive=None):
        """Assign each source CDR to its most specific ledger category."""
        record_id = record["record_id"]
        if record_id in seen_record_ids:
            return
        seen_record_ids.add(record_id)
        rows.append(_row(record, category, targets, distinctive))

    for r in repo.direct_contact_records(conn, dataset_id, phone_a, phone_b):
        append_once(r, "direct")
    for r in repo.records_for(conn, dataset_id, both, parties=shared_parties):
        append_once(r, "shared_contact",
                    distinctive=r["other_party"] in distinctive_parties)
    for category, areas in (("meet_up_location", meet_up_areas),
                            ("shared_location", shared_only_areas)):
        for r in repo.records_for(conn, dataset_id, both, areas=areas):
            append_once(r, category, distinctive=r["area"] in distinctive_areas)

    counts: dict[str, int] = {}
    for r in rows:
        counts[r["category"]] = counts.get(r["category"], 0) + 1

    return {
        "pair": {
            "dataset_id": dataset_id,
            "target_a": {"id": target_a["id"], "name": target_a["name"],
                         "phone_number": phone_a},
            "target_b": {"id": target_b["id"], "name": target_b["name"],
                         "phone_number": phone_b},
        },
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "rows": rows,
        "row_count": len(rows),
        "category_counts": counts,
    }
