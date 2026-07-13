# Conditional hub counting for the dataset mode

**Date:** 2026-07-14 · **Status:** DESIGN ONLY — approved by Khaled (co-founder/domain), NOT
implemented; flagged for Nadim before any code changes · **Amends:**
2026-07-13-adaptive-matcher-gates.md and the hub-exclusion decision in
2026-07-13-matcher-method-hardening-decisions.md

## Khaled's review verdict (2026-07-14)

Reviewing the merged method-hardening pass, Khaled **rejects the unconditional hub exclusion**
from the dataset-mode metric (`HUB_UBIQUITY_FRACTION` as currently applied in
`dataset_interconnectedness`). Two grounds:

1. **Distinctiveness already does the protective work at the finding level.** Two strangers
   sharing a taxi line get no mutual finding either way: a number shared by half the dataset is
   never rarer than the typical shared contact, so the rarity rule filters it in close-knit
   mode, and the ≥20% commonality discount filters it in strangers mode. The hub exclusion only
   stabilized the mode *label*.
2. **It deletes real family fabric from the close-knit signal.** In a family dataset, mom is
   contacted by everyone — the hub rule brands her a service and removes exactly the evidence
   that the dataset IS a close-knit group. A hub-and-spoke family could read "strangers" on the
   banner.

Khaled's direction: keep **rarity-based distinctiveness as the sole commonness mechanism** for
findings (unchanged), and make the mode metric treat mega-popular numbers by their
**prevalence**: many of them means group fabric, one or two means lone services.

## Design: conditional counting (Option A of three considered)

Terminology: a contact is **mega-popular** when its spread (distinct subscribers contacting it)
is ≥ 50% of subscribers — the same measurement the hub rule uses today, kept under a name that
no longer implies exclusion (suggested: `MEGA_POPULAR_FRACTION = 0.50`, PROPOSAL).

Let `M` = the count of mega-popular contacts in the dataset and `n` = subscribers.

- **Many** (`M ≥ max(2, 0.15 × n)`, both PROPOSALS — `MEGA_POPULAR_MANY_MIN = 2`,
  `MEGA_POPULAR_MANY_FRACTION = 0.15`): the mega-populars are family fabric (mom, dad, the
  group chat). **Include** them in the density sum Σ C(k,2)/C(n,2).
- **Few** (`M` below that line): they are lone services (a taxi line). **Exclude** them from
  the density sum — the current hardened behavior.

Everything else is untouched: the `CLOSE_KNIT_BOUNDARY = 2.0` decision, the margin/near-tie
classification tiers, the true shared-spread median (hubs ALWAYS stay in the median — the
`[2, 2, 100, 100] → 51` invariant holds), rarity-based close-knit distinctiveness including the
dropped `CK_SOLID_MEDIUM`, the strangers-mode 20% commonality discount, the `COMMON_MIN_USERS`
floor, and the small-population cap.

### Worked examples

- 12-person family; mom, dad, and the family group chat each contacted by 8+ members → `M = 3`,
  line = max(2, 1.8) = 2 → many → counted → density soars → **close-knit**. Mom is evidence FOR
  the family again.
- 40-subscriber strangers dataset; one taxi line at 55% spread → `M = 1`, line = max(2, 6) = 6
  → few → excluded → **strangers**. The lone service cannot flip the dataset.
- 200-subscriber dataset with two big services → `M = 2`, line = 30 → few → excluded →
  **strangers**. Scaling with `n` makes large datasets demand more evidence, which errs safe
  (genuinely close-knit populations are small).

### Known limitations (accepted)

- **Single-hub family:** a family whose ONLY shared number is mom (`M = 1 <
  MEGA_POPULAR_MANY_MIN`) still excludes her and can read strangers. Accepted: real family
  datasets nearly always carry ≥2 near-universal numbers, and findings between genuinely linked
  members still fire via direct contact / co-presence / rare mutuals.
- **A new cliff:** `M` crossing the many/few line flips what the density counts. Per the
  project's cliff-disclosure principle, implementation should extend `dataset_context` with a
  near-line note when `M` sits within 1 of the line (same spirit as the existing near-tie and
  near-boundary notes), so the flip is visible instead of silent.

### Superseded

- My (Claude's) earlier suggestion to simply lower the 50% threshold dies with the
  unconditional exclusion — prevalence, not a tighter cutoff, is the fix.
- `HUB_UBIQUITY_FRACTION`'s sign-off question in the 2026-07-13 handoff is answered by this
  design rather than by picking a new fraction.

## Not implemented

Per Khaled's instruction (2026-07-14): flag and document only. No code, threshold, fixture, or
test changes on this branch. Implementation waits for Nadim's agreement per the method-change
protocol (`COLLAB.md`); it touches `app/matching/repo.py` (`dataset_interconnectedness`),
`app/matching/gates.py` constants, both sample fixtures, and `tools/gen_matcher_scenarios.py`
when it happens.
