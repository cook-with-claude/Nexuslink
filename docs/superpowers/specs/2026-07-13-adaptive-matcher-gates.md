# Adaptive matcher gates: dataset modes, floors, and cliff transparency

**Date:** 2026-07-13 · **Status:** approved by Khaled (this branch), thresholds flagged for
Nadim/domain review as usual · **Extends:** 2026-07-12-contact-matcher-design.md

## Problems (found while testing the matcher against the scenario dataset)

1. **The distinctiveness gate assumes a strangers dataset.** "Common = contacted by ≥ 20% of
   other subscribers" discounts pizza places correctly in a broad population, but in a
   close-knit dataset (family, neighborhood — the expected use) *everyone's* real mutual
   friends cross 20%, so genuine mutual relationships are suppressed dataset-wide, sometimes
   to "no link" between people who visibly share a circle. A shared contact is still a FACT;
   gating a fact by its statistical interestingness deletes truth.
2. **The 20% rule breaks on tiny populations**: with 3 other subscribers, ONE other person
   contacting a number brands it common (0.2 × 3 = 0.6).
3. **A ↔ B is not perfectly symmetric**: co-presence events are deduped per (area, day) using
   target A's calendar day, so midnight-straddling meet-ups can merge differently depending on
   which box each name was put in — same pair, different event count.
4. **Cliffs are invisible**: every threshold is a hard line (49 records vs 50), and the new
   dataset-mode boundary adds a bigger one. Decision: cliffs are the accepted price of a
   legible tiered system (vs an opaque continuous score) — they are DISCLOSED, not removed.

## Design

### Dataset mode (per dataset, computed per match run)

Interconnectedness metric `D` = average number of shared contacts per subscriber pair
= Σ_c C(k_c, 2) / C(n, 2), where k_c = subscribers contacting party c, n = subscribers.
One GROUP BY; no O(n²) pass. `D ≥ CLOSE_KNIT_BOUNDARY` (2.0, PROPOSAL) → **close-knit**,
else **strangers**.

Every match payload carries `dataset_context`: mode, the metric, the boundary, subscriber
count, and a **classification confidence** tier from the margin `m = max(D,B)/min(D,B)`:
Near tie (m ≤ 1.15) / Low / Medium (≥ 1.4) / High (≥ 2.0). The UI renders this as a line of
text above the findings — the mode cliff is disclosed with its own strength rating, and a
dataset sitting on the line says "near tie" out loud.

### Strangers mode — existing gate + commonality floor

Unchanged except: common now requires `users_with ≥ max(COMMON_MIN_USERS=3,
20% × other_users)` — one coincidental other subscriber can never delete evidence again.
New caveat when `0 < other_users < SMALL_POPULATION=10`: too few subscribers to reliably
judge commonality (applies in both modes; the mode metric is equally crude there).

### Close-knit mode — mutual finding rates rarity, never suppresses

- Fires on **any** shared contact (the ≥ 2-distinctive floor is strangers-mode only): in a
  clique, sharing contacts is a real mutual relationship — the question is only how special.
- Per-contact "rare" is judged **relative to the dataset**: shared by fewer subscribers than
  the dataset's median *shared*-contact spread (k ≥ 2 contacts only — a median over all
  contacts would always be 1, since most contacts anywhere are personal).
- The distinctiveness gate becomes **count-based**, not ratio-based (extra group fabric on
  top of rare mutuals must never LOWER a rating): ≥ `CK_RARE_HIGH=2` rare shared contacts →
  High (a private link beyond the fabric); solid overlap (≥ `CK_SOLID_MEDIUM=3` shared, or
  exactly 1 rare) → Medium (real mutuals, nothing pair-specific); else Low (trivial overlap).
  Sample / overlap share / window overlap gates unchanged.
- Area commonality (co-presence) keeps the absolute 20% rule in BOTH modes: a busy mall is a
  busy mall regardless of dataset type.

### Symmetry

`compute_match` canonicalizes the pair (sorted by phone number) before gathering facts, so
A-vs-B and B-vs-A are byte-identical (the response's `pair` reflects canonical order; saved
pair identity was already order-normalized).

### Gate-cliff disclosure

Each finding carries `notes`: one line per gate whose raw value sits near a tier line
(within 10%, minimum slack 1 for integer gates) — e.g. "sample is just short of High: 49
records vs 50" or "event count barely clears Medium: 3 vs 2". Ratings stay pure tiers
(bound_by/min() untouched); notes are parallel text. The UI renders them under the
binding note; old saved payloads without the fields render unchanged.

## Compatibility

`build_findings` reads the new facts via `.get()` with strangers-mode defaults, so old
fabricated-facts tests and old stored payloads keep working. The scenario workbook gains a
close-knit companion dataset (`sample_matcher_closeknit.xlsx`) with an ordinary clique pair
(Medium, group-wide contacts) and a standout pair (High, rare shared mutuals); the generator
moves into `tools/gen_matcher_scenarios.py`.

## Flagged constants (PROPOSALS, same protocol as every matcher threshold)

`CLOSE_KNIT_BOUNDARY=2.0`, mode-confidence margins `2.0/1.4/1.15`, `COMMON_MIN_USERS=3`,
`SMALL_POPULATION=10`, `NEAR_BOUNDARY_FRACTION=0.10`, `CK_RARE_HIGH=2`, `CK_SOLID_MEDIUM=3`,
rarity = strictly below the median shared-contact spread.
