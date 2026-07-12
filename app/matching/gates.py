"""Pure gate engine for the contact matcher (DOMAIN layer, no SQL, no Flask).

Rates a pair of targets from pre-gathered facts into typed FINDINGS, each with a
weakest-link High/Medium/Low strength. Three finding types, each a distinct claim:

- direct_contact  "Direct contact"      they call/text each other
- mutual_contacts "Mutual relationship" they share a meaningful, distinctive
                                        set of third-party contacts
- co_presence     "Meeting up"          repeatedly in the same area at the
                                        same time

Design rules (spec 2026-07-12-contact-matcher-design.md):
- Findings coexist; there is never a single blended relationship score.
- Strength = min() of the gates applicable to THAT finding type. Direct contact
  is positive evidence, not a doubt, so it is rated by its own volume and never
  folded into a min() with the doubt gates.
- Every finding records which gate(s) bound its strength (`bound_by`).
- Shared areas WITHOUT time overlap are a detail row, never a finding.

ALL THRESHOLDS ARE PROPOSALS pending Nadim/domain review (same protocol as the
Phase-1 gate thresholds). N reuses the Phase-1 values.
"""

from __future__ import annotations

from datetime import date

HIGH, MEDIUM, LOW = "High", "Medium", "Low"
_ORDER = {LOW: 0, MEDIUM: 1, HIGH: 2}

# Sample gate (records per side; the weaker-observed target caps everything).
N_HIGH, N_MEDIUM = 50, 15
# Window-overlap gate: overlapping days / the shorter observation span's days.
WINDOW_HIGH, WINDOW_MEDIUM = 0.60, 0.20
# Overlap-share gate: shared contacts / the smaller side's contact circle.
SHARE_HIGH, SHARE_MEDIUM = 0.40, 0.15
# Distinctiveness gate: fraction of the pair's shared contacts (or meet-up
# events' areas) that are NOT dataset-common.
DISTINCT_HIGH, DISTINCT_MEDIUM = 0.60, 0.30
# A shared contact/area is "common" when >= this fraction of OTHER subscribers
# also has it (the pizza-place / busy-tower discount).
COMMON_USER_FRACTION = 0.20
# Event-count gate (meet-up events, deduped per area+day).
EVENTS_HIGH, EVENTS_MEDIUM = 5, 2
# Direct-contact volume rating.
DIRECT_HIGH, DIRECT_MEDIUM = 10, 3
# The mutual finding fires only from this many distinctive shared contacts.
MUTUAL_MIN_DISTINCTIVE = 2

LABELS = {
    "direct_contact": "Direct contact",
    "mutual_contacts": "Mutual relationship",
    "co_presence": "Meeting up",
}


def _tier(value, high, medium) -> str:
    if value >= high:
        return HIGH
    if value >= medium:
        return MEDIUM
    return LOW


def weakest(gate_ratings: dict[str, str]) -> tuple[str, list[str]]:
    """min() of the gates plus every gate name sitting at that minimum."""
    strength = min(gate_ratings.values(), key=_ORDER.get)
    bound_by = [name for name, r in gate_ratings.items() if r == strength]
    return strength, bound_by


def _days(span: tuple[str, str]) -> tuple[date, date]:
    return (date.fromisoformat(span[0][:10]), date.fromisoformat(span[1][:10]))


def window_overlap_ratio(span_a, span_b) -> float:
    """Overlapping days / the SHORTER span's days (both endpoints inclusive, so a
    single-day span is 1 day, not 0). 0.0 when the spans don't touch."""
    a_lo, a_hi = _days(span_a)
    b_lo, b_hi = _days(span_b)
    overlap = (min(a_hi, b_hi) - max(a_lo, b_lo)).days + 1
    if overlap <= 0:
        return 0.0
    shorter = min((a_hi - a_lo).days, (b_hi - b_lo).days) + 1
    return min(1.0, overlap / shorter)


def _is_common(users_with: int, other_users: int) -> bool:
    # With no other subscribers to compare against, commonness is unmeasurable;
    # treat the item as distinctive rather than inventing a discount.
    if other_users == 0:
        return False
    return users_with >= COMMON_USER_FRACTION * other_users


def _direct_finding(facts: dict) -> dict | None:
    d = facts["direct"]
    if d["total"] < 1:
        return None
    if d["a_to_b"] and d["b_to_a"]:
        direction = "both directions"
    elif d["a_to_b"]:
        direction = f"{facts['name_a']} → {facts['name_b']} only"
    else:
        direction = f"{facts['name_b']} → {facts['name_a']} only"
    return {
        "type": "direct_contact",
        "label": LABELS["direct_contact"],
        "strength": _tier(d["total"], DIRECT_HIGH, DIRECT_MEDIUM),
        "bound_by": ["direct volume"],
        "headline": f"{d['total']}× ({d['calls']} calls, {d['sms']} SMS, {direction})",
        "evidence": dict(d),
    }


def _mutual_finding(facts: dict, window_rating: str) -> dict | None:
    contacts_a, contacts_b = facts["contacts_a"], facts["contacts_b"]
    shared = sorted(set(contacts_a) & set(contacts_b))
    if not shared:
        return None
    commonality = facts["contact_commonality"]
    other_users = facts["other_users"]
    distinctive = [p for p in shared if not _is_common(commonality.get(p, 0), other_users)]
    if len(distinctive) < MUTUAL_MIN_DISTINCTIVE:
        return None

    smaller_circle = min(len(contacts_a), len(contacts_b))
    ratings = {
        "sample": _tier(min(facts["n_a"], facts["n_b"]), N_HIGH, N_MEDIUM),
        "overlap share": _tier(len(shared) / smaller_circle, SHARE_HIGH, SHARE_MEDIUM),
        "distinctiveness": _tier(len(distinctive) / len(shared), DISTINCT_HIGH, DISTINCT_MEDIUM),
        "window overlap": window_rating,
    }
    strength, bound_by = weakest(ratings)
    share_a = len(shared) / len(contacts_a)
    share_b = len(shared) / len(contacts_b)
    return {
        "type": "mutual_contacts",
        "label": LABELS["mutual_contacts"],
        "strength": strength,
        "bound_by": bound_by,
        "headline": (f"{len(shared)} shared contacts "
                     f"({share_a:.0%} of {facts['name_a']}'s circle, "
                     f"{share_b:.0%} of {facts['name_b']}'s)"),
        "evidence": {
            "gates": ratings,
            "shared_contacts": [
                {"party": p, "count_a": contacts_a[p], "count_b": contacts_b[p],
                 "other_users_with": commonality.get(p, 0),
                 "distinctive": p in distinctive}
                for p in shared
            ],
        },
    }


def _co_presence_finding(facts: dict, window_rating: str) -> dict | None:
    events = facts["co_events"]
    if not events:
        return None
    commonality = facts["area_commonality"]
    other_users = facts["other_users"]
    distinctive_events = [
        e for e in events if not _is_common(commonality.get(e["area"], 0), other_users)
    ]
    days = {e["day"] for e in events}
    ratings = {
        "sample": _tier(min(facts["n_a"], facts["n_b"]), N_HIGH, N_MEDIUM),
        "event count": _tier(len(events), EVENTS_HIGH, EVENTS_MEDIUM),
        "location distinctiveness": _tier(
            len(distinctive_events) / len(events), DISTINCT_HIGH, DISTINCT_MEDIUM),
        "window overlap": window_rating,
    }
    strength, bound_by = weakest(ratings)
    return {
        "type": "co_presence",
        "label": LABELS["co_presence"],
        "strength": strength,
        "bound_by": bound_by,
        "headline": (f"{len(events)} co-located event(s) across {len(days)} day(s)"),
        "evidence": {
            "gates": ratings,
            "events": [
                {**e, "other_users_with": commonality.get(e["area"], 0)}
                for e in events
            ],
        },
    }


def build_findings(facts: dict) -> dict:
    """facts -> {findings, caveats, details, no_link}. See repo.py for how each
    fact is gathered; this function is deliberately I/O-free so every scenario is
    unit-testable with a plain dict."""
    caveats: list[str] = []

    empty = [name for name, n in
             ((facts["name_a"], facts["n_a"]), (facts["name_b"], facts["n_b"])) if n == 0]
    if empty:
        for name in empty:
            caveats.append(f"{name} has no records; absence of overlap is not meaningful.")
        return {"findings": [], "caveats": caveats,
                "details": {"windows": None, "shared_areas_no_time_overlap": []},
                "no_link": True}

    ratio = window_overlap_ratio(facts["span_a"], facts["span_b"])
    window_rating = _tier(ratio, WINDOW_HIGH, WINDOW_MEDIUM)
    if ratio < WINDOW_MEDIUM:
        caveats.append(
            f"The two observation windows overlap only {ratio:.0%}; "
            "absence of overlap is not meaningful.")

    findings = [f for f in (
        _direct_finding(facts),
        _mutual_finding(facts, window_rating),
        _co_presence_finding(facts, window_rating),
    ) if f is not None]

    co_areas = {e["area"] for e in facts["co_events"]}
    shared_areas_only = sorted((facts["areas_a"] & facts["areas_b"]) - co_areas)

    return {
        "findings": findings,
        "caveats": caveats,
        "details": {
            "windows": {"a": list(facts["span_a"]), "b": list(facts["span_b"]),
                        "overlap_ratio": round(ratio, 4)},
            "shared_areas_no_time_overlap": shared_areas_only,
        },
        "no_link": not findings,
    }
