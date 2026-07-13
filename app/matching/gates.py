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
# The mutual finding fires only from this many distinctive shared contacts
# (STRANGERS mode only -- in a close-knit dataset shared contacts are a fact,
# never suppressed; see the 2026-07-13 adaptive-gates spec).
MUTUAL_MIN_DISTINCTIVE = 2
# Close-knit distinctiveness rating (count-based, not ratio: sharing MORE group
# fabric on top of rare mutuals must never LOWER a rating). High = at least this
# many rare shared contacts (pair-specific mutuals beyond the group's fabric);
# Medium = solid overlap that is all group-wide; below that, trivial overlap.
CK_RARE_HIGH = 2
CK_SOLID_MEDIUM = 3

# ---- adaptive dataset mode (spec 2026-07-13-adaptive-matcher-gates.md) ----
# A fixed "common" cutoff assumes a strangers dataset; in a close-knit group
# (family, neighborhood) everyone's real mutual friends cross it and genuine
# relationships get suppressed. The dataset itself picks the rules: its measured
# interconnectedness (average shared contacts per subscriber pair) classifies it
# strangers vs close-knit, and the classification is DISCLOSED with its own
# confidence tier because the boundary is a cliff -- a dataset near the line says
# "near tie" out loud instead of silently flipping modes between imports.
CLOSE_KNIT, STRANGERS = "close-knit", "strangers"
CLOSE_KNIT_BOUNDARY = 2.0            # avg shared contacts per pair (PROPOSAL)
MODE_MARGIN_HIGH, MODE_MARGIN_MEDIUM = 2.0, 1.4   # classification confidence
MODE_NEAR_TIE = 1.15                 # within 15% of the boundary = near tie
# Commonality floor: a contact/area is never "common" on the say-so of fewer
# than this many other subscribers (0.2 * 3 others = 0.6 would otherwise let a
# single coincidental caller delete evidence in a tiny population).
COMMON_MIN_USERS = 3
# Below this many other subscribers, commonality (and the mode metric) is too
# crude to trust -- surfaced as a caveat, the math is left alone.
SMALL_POPULATION = 10
# Gate-cliff disclosure: a raw value within this fraction of a tier line (with a
# minimum slack of 1 for integer-valued gates) gets a per-finding note, so a
# 49-vs-50 near miss is visible instead of buried under "Medium".
NEAR_BOUNDARY_FRACTION = 0.10

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
    # The COMMON_MIN_USERS floor keeps a single coincidental other caller from
    # branding a contact common when the population is tiny.
    return users_with >= max(COMMON_MIN_USERS, COMMON_USER_FRACTION * other_users)


def classify_dataset(density: float) -> dict:
    """Strangers vs close-knit from the dataset's interconnectedness (average
    shared contacts per subscriber pair), plus a confidence tier for the
    classification itself: the mode boundary is a hard line, so how decisively
    the dataset sits on its side is part of the answer. `Near tie` means the
    dataset is ON the line and ratings may flip with small data changes."""
    boundary = CLOSE_KNIT_BOUNDARY
    mode = CLOSE_KNIT if density >= boundary else STRANGERS
    margin = float("inf") if density <= 0 else max(density, boundary) / min(density, boundary)
    if margin <= MODE_NEAR_TIE:
        classification = "Near tie"
    elif margin >= MODE_MARGIN_HIGH:
        classification = HIGH
    elif margin >= MODE_MARGIN_MEDIUM:
        classification = MEDIUM
    else:
        classification = LOW
    return {"mode": mode, "classification": classification,
            "avg_shared_contacts_per_pair": round(density, 2), "boundary": boundary}


def _near_note(label: str, value: float, high: float, medium: float,
               integer: bool = False) -> str | None:
    """A disclosure line when `value` sits near one of its tier lines. Ratings
    stay pure tiers (the min()/bound_by logic never sees this); the note rides
    alongside so a near miss is visible instead of buried under the tier."""
    boundary = min((high, medium), key=lambda t: abs(value - t))
    slack = NEAR_BOUNDARY_FRACTION * boundary
    if integer:
        slack = max(slack, 1)
    if abs(value - boundary) > slack:
        return None
    tier = HIGH if boundary == high else MEDIUM
    show = (lambda v: str(int(v))) if integer else (lambda v: f"{v:.2f}")
    if value < boundary:
        return f"{label} is just short of {tier}: {show(value)} vs {show(boundary)}"
    return f"{label} barely clears {tier}: {show(value)} vs {show(boundary)}"


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
        "notes": [n for n in (
            _near_note("direct volume", d["total"], DIRECT_HIGH, DIRECT_MEDIUM,
                       integer=True),
        ) if n],
        "headline": f"{d['total']}× ({d['calls']} calls, {d['sms']} SMS, {direction})",
        "evidence": dict(d),
    }


def _mutual_finding(facts: dict, window_rating: str, window_ratio: float,
                    mode: str, spread_median: int) -> dict | None:
    contacts_a, contacts_b = facts["contacts_a"], facts["contacts_b"]
    shared = sorted(set(contacts_a) & set(contacts_b))
    if not shared:
        return None
    commonality = facts["contact_commonality"]
    other_users = facts["other_users"]
    if mode == CLOSE_KNIT:
        # In a clique the fixed cutoff brands everyone's real friends "common".
        # Sharing contacts is a FACT there -- the finding always fires; what gets
        # graded is how pair-specific the overlap is. "Rare" = shared by fewer
        # subscribers than the dataset's typical SHARED contact. The pair itself
        # is part of a shared contact's spread (commonality counts OTHERS), so
        # +2 puts both sides of the comparison on the same base. Count-based:
        # >= CK_RARE_HIGH rare mutuals -> High (a private link beyond the group
        # fabric); solid but all group-wide -> Medium; trivial overlap -> Low.
        distinctive = [p for p in shared if commonality.get(p, 0) + 2 < spread_median]
        if len(distinctive) >= CK_RARE_HIGH:
            distinct_rating = HIGH
        elif len(distinctive) == 1 or len(shared) >= CK_SOLID_MEDIUM:
            distinct_rating = MEDIUM
        else:
            distinct_rating = LOW
        distinct_note = _near_note("rare shared contacts", len(distinctive),
                                   CK_RARE_HIGH, CK_RARE_HIGH, integer=True)
    else:
        distinctive = [p for p in shared
                       if not _is_common(commonality.get(p, 0), other_users)]
        if len(distinctive) < MUTUAL_MIN_DISTINCTIVE:
            return None
        distinct_ratio = len(distinctive) / len(shared)
        distinct_rating = _tier(distinct_ratio, DISTINCT_HIGH, DISTINCT_MEDIUM)
        distinct_note = _near_note("distinctiveness", distinct_ratio,
                                   DISTINCT_HIGH, DISTINCT_MEDIUM)

    smaller_circle = min(len(contacts_a), len(contacts_b))
    share_ratio = len(shared) / smaller_circle
    sample = min(facts["n_a"], facts["n_b"])
    ratings = {
        "sample": _tier(sample, N_HIGH, N_MEDIUM),
        "overlap share": _tier(share_ratio, SHARE_HIGH, SHARE_MEDIUM),
        "distinctiveness": distinct_rating,
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
        "notes": [n for n in (
            _near_note("sample", sample, N_HIGH, N_MEDIUM, integer=True),
            _near_note("overlap share", share_ratio, SHARE_HIGH, SHARE_MEDIUM),
            distinct_note,
            _near_note("window overlap", window_ratio, WINDOW_HIGH, WINDOW_MEDIUM),
        ) if n],
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


def _co_presence_finding(facts: dict, window_rating: str,
                         window_ratio: float) -> dict | None:
    events = facts["co_events"]
    if not events:
        return None
    commonality = facts["area_commonality"]
    other_users = facts["other_users"]
    # Areas keep the absolute commonality rule in BOTH dataset modes: a busy
    # mall is a busy mall whether the subscribers are strangers or a clique.
    distinctive_events = [
        e for e in events if not _is_common(commonality.get(e["area"], 0), other_users)
    ]
    days = {e["day"] for e in events}
    sample = min(facts["n_a"], facts["n_b"])
    distinct_ratio = len(distinctive_events) / len(events)
    ratings = {
        "sample": _tier(sample, N_HIGH, N_MEDIUM),
        "event count": _tier(len(events), EVENTS_HIGH, EVENTS_MEDIUM),
        "location distinctiveness": _tier(distinct_ratio, DISTINCT_HIGH, DISTINCT_MEDIUM),
        "window overlap": window_rating,
    }
    strength, bound_by = weakest(ratings)
    return {
        "type": "co_presence",
        "label": LABELS["co_presence"],
        "strength": strength,
        "bound_by": bound_by,
        "notes": [n for n in (
            _near_note("sample", sample, N_HIGH, N_MEDIUM, integer=True),
            _near_note("event count", len(events), EVENTS_HIGH, EVENTS_MEDIUM,
                       integer=True),
            _near_note("location distinctiveness", distinct_ratio,
                       DISTINCT_HIGH, DISTINCT_MEDIUM),
            _near_note("window overlap", window_ratio, WINDOW_HIGH, WINDOW_MEDIUM),
        ) if n],
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
    """facts -> {findings, caveats, details, dataset_context, no_link}. See
    repo.py for how each fact is gathered; this function is deliberately I/O-free
    so every scenario is unit-testable with a plain dict. The dataset-mode facts
    are read with strangers-mode defaults so payloads/tests predating the
    adaptive gates keep their exact old behavior."""
    caveats: list[str] = []
    dataset_context = classify_dataset(facts.get("dataset_density", 0.0))
    dataset_context["subscribers"] = facts.get("other_users", 0) + 2
    spread_median = facts.get("contact_spread_median", 2)

    other_users = facts.get("other_users", 0)
    if 0 < other_users < SMALL_POPULATION:
        caveats.append(
            f"Only {other_users} other subscriber(s) in this dataset — too few to "
            "reliably judge which contacts or places are common.")

    empty = [name for name, n in
             ((facts["name_a"], facts["n_a"]), (facts["name_b"], facts["n_b"])) if n == 0]
    if empty:
        for name in empty:
            caveats.append(f"{name} has no records; absence of overlap is not meaningful.")
        return {"findings": [], "caveats": caveats,
                "details": {"windows": None, "shared_areas_no_time_overlap": []},
                "dataset_context": dataset_context,
                "no_link": True}

    ratio = window_overlap_ratio(facts["span_a"], facts["span_b"])
    window_rating = _tier(ratio, WINDOW_HIGH, WINDOW_MEDIUM)
    if ratio < WINDOW_MEDIUM:
        caveats.append(
            f"The two observation windows overlap only {ratio:.0%}; "
            "absence of overlap is not meaningful.")

    findings = [f for f in (
        _direct_finding(facts),
        _mutual_finding(facts, window_rating, ratio,
                        dataset_context["mode"], spread_median),
        _co_presence_finding(facts, window_rating, ratio),
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
        "dataset_context": dataset_context,
        "no_link": not findings,
    }
