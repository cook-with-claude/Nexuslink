# Contact matcher method decision memo

**Date:** 2026-07-13

**Status:** Nadim decision required; no method or threshold change applied

**Source:** independent review findings 1, 6, 7, 8, 9, and 10

This memo separates method decisions from the mechanical review fixes. Each item
changes what a finding means or how strongly it is rated, so none should be
implemented without Nadim's sign-off and scenario recalibration.

## 1. Dataset mode can be driven by universal hubs

**Observed risk.** `D` counts every shared contact equally. A few service numbers
used by nearly everyone can therefore classify unrelated subscribers as a
close-knit dataset, after which group-wide overlap is deliberately retained as a
mutual finding.

**Proposed change.** Classify mode from two disclosed values: raw `D` and a
hub-adjusted `D` that excludes contacts above a dataset-wide prevalence ceiling.
Enter close-knit mode only when adjusted `D` also clears its calibrated boundary.
Keep raw `D` in the payload so analysts can see why the two measures differ.

**Tradeoff.** A real family or neighborhood may genuinely share highly prevalent
contacts, so hub removal can misclassify the exact close-knit datasets this mode
was added to support. CDR topology alone may not distinguish a community contact
from a commercial service; this needs scenario distributions, not an intuitive
ceiling chosen in isolation.

## 6. Calendar-day co-presence dedup is not a session model

**Observed risk.** One continuous meeting across midnight becomes two events,
while two separate meetings in one area on the same day become one. Event-count
strength can move in either direction.

**Proposed change.** Build candidate time pairs as today, then cluster them into
sessions per area using a disclosed maximum inter-hit gap. A cluster spanning
midnight remains one event; sufficiently separated clusters on the same day can
become separate events.

**Tradeoff.** This introduces another threshold, increases query/processing cost,
and can split a long meeting or merge distinct meetings depending on the chosen
gap. The existing day rule is crude but very legible and cheap.

## 7. Even-cardinality spread uses the lower middle

**Observed risk.** For spreads such as `[2, 2, 100, 100]`, the implementation's
median is `2`; the conventional median is `51`. That materially changes which
pair-private contacts are rare in close-knit mode.

**Proposed change.** Use the arithmetic mean of the two middle values for even
populations, and add explicit odd/even and bimodal scenario cases. Store the raw
median in `dataset_context` for review.

**Tradeoff.** In a bimodal dataset, the arithmetic midpoint may describe no actual
contact and can classify the entire lower cluster as rare. Keeping the lower
median is more conservative, but then it should be named `lower_median` rather
than presented as the conventional statistic.

## 8. Mutual sample size counts unrelated records

**Observed risk.** Location-only or otherwise unrelated CDRs can clear the mutual
finding's `N` gate even when only a handful of contact-bearing records support the
shared-contact claim.

**Proposed change.** Make sample size finding-specific. For mutual contacts, use
each side's total contact-bearing record count (not only shared-contact rows, which
would make the gate circular). Keep the current all-record sample for co-presence,
where every record contributes an area observation.

**Tradeoff.** Strengths become less directly comparable across finding types, and
datasets rich in location observations but sparse in counterparties will rate
mutual findings lower than today. Separate thresholds must be calibrated for the
new denominator; reusing `50/15` would not be justified automatically.

## 9. The commonality floor overprotects very small populations

**Observed risk.** When fewer than three other subscribers exist, even a contact
used by all of them cannot be common. The caveat is textual only, so a strong
mutual finding can still be built from statistically unjudgeable distinctiveness.

**Proposed change.** Treat distinctiveness as unscorable below a minimum comparison
population and cap that gate at Low (or return an explicit `Insufficient context`
state) instead of treating every item as distinctive. Keep the current floor once
the population is large enough to satisfy it.

**Tradeoff.** This prevents strong ratings in small family datasets and partially
reintroduces the evidence-suppression problem the floor was designed to solve. An
explicit unscorable state is more honest but expands the current three-tier model
and every UI/export consumer.

## 10. Mirrored CDR legs inflate direct volume

**Observed risk.** If one physical call appears as A-out and B-in records, direct
volume counts two interactions. Strength therefore depends on whether an import
contains one leg or both.

**Proposed change.** Prefer an operator-provided event/call identifier when one is
available. Without one, either (a) deliberately rename the metric to `direct CDR
rows` and calibrate it as such, or (b) introduce conservative mirror matching on
opposite direction, timestamp, duration, and parties, while retaining both raw
rows in the ledger.

**Tradeoff.** Heuristic mirror matching can collapse legitimate simultaneous or
repeated calls, and the current schema has no stable event ID to prove equivalence.
Keeping row volume is fully auditable but leaves strength dependent on export
encoding. This decision should follow the expected synthetic generator format.

## Sign-off checklist

Nadim should decide each item independently, then require regenerated scenario
workbooks plus explicit before/after expected outcomes. A decision to keep current
behavior should update the design text to name the chosen statistic or limitation
precisely; it should not remain implicit in code.
