# Matcher evidence counters

**Date:** 2026-07-13 · **Status:** approved by Khaled (this branch) ·
**Extends:** 2026-07-12-contact-matcher-design.md, 2026-07-13-adaptive-matcher-gates.md

## Problem

The matcher reports gated *verdicts* but never states the raw evidence they rest on. The
numbers exist only inside each finding's evidence table, and one signal is missing entirely:

- **Direct records** — counted, but buried in the direct-contact finding.
- **Mutual calls** — we count *how many contacts* are shared, never the **record volume** with
  them (A called their 5 shared contacts 20×, B 27× → 47 mutual-call records: a number the tool
  cannot currently produce).
- **Mutual locations** — barely exists. A shared area with no time overlap is a bare name in a
  footnote (`details.shared_areas_no_time_overlap`), with **no counts at all**. "Mutual
  locations" (both frequent this area) is a different claim from "meeting up" (both there at
  the same time), and only the latter is measured today.

An analyst asking "how much evidence is there?" has no single answer, and nothing to export.

## Design

### Semantics — counts, not verdicts

The counters are **descriptive tallies**: no confidence, no strength pills, no gates. This is
the rule already set for frequent areas and the frequency explorer (a count is not a gated
verdict). The findings sit above the counter and are where judgment happens; the counter states
what is in the data. Every count is derived from the SAME facts the gates used, so the two can
never disagree.

Three categories, each split in two buckets:

| Category | Bucket A | Bucket B |
|---|---|---|
| **Direct contact** | (not split) totals: records, calls, SMS, A→B, B→A | — |
| **Mutual calls** | with **distinctive** shared contacts | with **common** shared contacts |
| **Mutual locations** | **meet-up** areas (co-presence happened there) | **non-meet-up** shared areas |

Each bucket carries: how many items (contacts / areas) and the record volume — for mutual calls
the volume split per side (A's records with them, B's records with them); for locations each
side's visit counts in those areas.

"Distinctive vs common" reuses the gate engine's existing per-contact classification, which is
**dataset-mode aware** (adaptive-gates spec): in strangers mode "common" = the 20%-of-others
discount (with the `COMMON_MIN_USERS` floor); in close-knit mode "common" = not rarer than the
median shared-contact spread. The counter therefore labels contacts exactly as the finding above
it does — one classification, two consumers.

**Disjointness rule:** the location buckets are disjoint **by area**. An area where the pair met
AND both separately frequent counts in the meet-up bucket only, never both, so bucket totals sum
to the shared-area total without double counting.

### Data flow

`repo.py` gains ONE new query: `area_tallies(conn, dataset_id, phone)` → `{area: record_count}`
(today we fetch only the *set* of areas, so per-area volume is unavailable). `service.py`
composes `evidence_counts` from the existing facts plus that query, and `gates.py` grows a pure
`build_evidence_counts(facts)` — I/O-free like the rest of the engine, so every count is
unit-testable from a plain dict. It reuses the same distinctive/common classifier the mutual
finding uses (extracted to a helper so the two cannot drift).

Payload gains a sibling of `findings`:

```jsonc
"evidence_counts": {
  "direct": {"records": 12, "calls": 8, "sms": 4, "a_to_b": 6, "b_to_a": 6},
  "mutual_calls": {
    "distinctive": {"contacts": 5, "records_a": 20, "records_b": 27, "records": 47},
    "common":      {"contacts": 2, "records_a": 4,  "records_b": 6,  "records": 10}
  },
  "mutual_locations": {
    "meet_up":     {"areas": 3, "records_a": 18, "records_b": 15, "records": 33},
    "non_meet_up": {"areas": 4, "records_a": 22, "records_b": 19, "records": 41}
  }
}
```

Absent on payloads saved before this change → UI and export render "—" (same rule as
`dataset_context`). The save endpoints already recompute server-side, so re-saving a pair fills
it in.

### UI — strip on top, detail inside

In the matcher card, between the dataset-mode banner and the findings: a compact **evidence
strip** (always visible), reading e.g.
`Direct 12 · Mutual calls 47 across 5 contacts · Locations 3 meet-up / 4 shared-only`.
Clicking it expands a small table with the per-bucket breakdown and each side's record counts.
Styled as a tally (muted, mono numbers, **no pill**) so it can never be mistaken for a verdict.

### Excel — a new "Evidence counts" sheet

One row per **saved pair** (item-level detail is already digested in the `Contact matches` sheet's
*Key evidence* column and shown in full in the UI, so a second item-level sheet would duplicate
it). Always present, placeholder row when nothing is saved — the workbook's shape stays
predictable, matching every other sheet.

Columns: `Pair ID | Dataset | Target A | Target B | Saved at | Direct records | Calls | SMS |
A→B | B→A | Shared contacts (distinctive) | Mutual-call records (distinctive) | Shared contacts
(common) | Mutual-call records (common) | Meet-up areas | Meet-up records | Shared-only areas |
Shared-only records`.

Appended as a NEW sheet — existing sheets and their column indices are untouched.

### Testing

- `gates.build_evidence_counts` unit tests from fabricated facts: both splits, the disjointness
  rule (a meet-up area is never also counted as shared-only), zero/empty cases, and that the
  distinctive/common classification matches the mutual finding's in BOTH dataset modes.
- End-to-end assertion on the existing fixture pair (hand-worked counts).
- Export test: the new sheet's headers, one populated row, and the placeholder row.
- `components.test.mjs`: the strip renders its summary line; a payload without
  `evidence_counts` renders unchanged (no strip, no crash).
- `docs/matcher-test-scenarios.md` gains the expected counts for the scenario pairs, verified by
  `tools/gen_matcher_scenarios.py` like every other expectation.

## Out of scope

No new gates, thresholds, or ratings — the counter cannot change any existing verdict. No
cross-pair "who has the most evidence" ranking (a plausible follow-up; not asked for).
