"""Contact-matcher orchestration (DOMAIN layer): gather facts, rate, wrap.

The one place that knows which repo facts feed which gate inputs. Takes a
caller-supplied connection like a repo, returns the full payload the route
serves, the save endpoint persists, and the export copies. No Flask, no audit,
no commit -- the route owns the unit-of-work.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.matching import gates, repo


def compute_match(conn, target_a: dict, target_b: dict) -> dict:
    """Full findings payload for two targets of the same dataset. Callers
    validate targets exist / same dataset / distinct before calling."""
    # Canonical pair order: co-presence events are deduped per (area, day) keyed
    # to A's calendar day, so midnight-straddling meet-ups could merge differently
    # depending on which box each name was put in. Sorting here makes A-vs-B and
    # B-vs-A byte-identical (the response's `pair` reflects canonical order; saved
    # pair identity was already order-normalized).
    if target_b["phone_number"] < target_a["phone_number"]:
        target_a, target_b = target_b, target_a
    dataset_id = target_a["dataset_id"]
    phone_a, phone_b = target_a["phone_number"], target_b["phone_number"]

    # The pair's own numbers are excluded from "contacts": talking to each other
    # is the direct-contact finding, not a shared third party.
    contacts_a = repo.contact_tallies(conn, dataset_id, phone_a, exclude=(phone_a, phone_b))
    contacts_b = repo.contact_tallies(conn, dataset_id, phone_b, exclude=(phone_a, phone_b))
    shared_parties = set(contacts_a) & set(contacts_b)
    # Per-area volume (evidence counter) subsumes the plain area set the gates
    # need, so one query per side serves both.
    area_tallies_a = repo.area_tallies(conn, dataset_id, phone_a)
    area_tallies_b = repo.area_tallies(conn, dataset_id, phone_b)
    areas_a, areas_b = set(area_tallies_a), set(area_tallies_b)
    co_events = repo.co_presence_events(conn, dataset_id, phone_a, phone_b)
    co_areas = {e["area"] for e in co_events}

    facts = {
        "name_a": target_a["name"], "name_b": target_b["name"],
        "n_a": repo.record_count(conn, dataset_id, phone_a),
        "n_b": repo.record_count(conn, dataset_id, phone_b),
        "span_a": repo.observation_span(conn, dataset_id, phone_a),
        "span_b": repo.observation_span(conn, dataset_id, phone_b),
        "contacts_a": contacts_a, "contacts_b": contacts_b,
        "areas_a": areas_a, "areas_b": areas_b,
        "area_tallies_a": area_tallies_a, "area_tallies_b": area_tallies_b,
        "direct": repo.direct_contact(conn, dataset_id, phone_a, phone_b),
        "co_events": co_events,
        "other_users": repo.other_user_count(conn, dataset_id, phone_a, phone_b),
        "contact_commonality": repo.contact_commonality(
            conn, dataset_id, shared_parties, phone_a, phone_b),
        "area_commonality": repo.area_commonality(
            conn, dataset_id, co_areas, phone_a, phone_b),
        # Dataset-level mode facts (adaptive gates, spec 2026-07-13).
        **repo.dataset_interconnectedness(conn, dataset_id),
    }

    result = gates.build_findings(facts)
    return {
        "pair": {
            "dataset_id": dataset_id,
            "target_a": {"id": target_a["id"], "name": target_a["name"],
                         "phone_number": phone_a},
            "target_b": {"id": target_b["id"], "name": target_b["name"],
                         "phone_number": phone_b},
        },
        "computed_at": datetime.now(timezone.utc).isoformat(),
        **result,
    }
