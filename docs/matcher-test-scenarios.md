# Contact-matcher test datasets

Two synthetic CDR datasets (May 2026) that together exercise **every outcome the
contact matcher can produce** — one per dataset mode (adaptive gates, spec
2026-07-13):

- **`sample_matcher_scenarios.xlsx`** (1716 rows, 40 subscribers) — a **strangers**
  dataset: pairs P01–P15 cover each finding type at every strength, every gate as
  the binding (weakest) gate, the common-contact/common-area discount, the
  disjoint-window caveat, the shared-area detail row, and no-link.
- **`sample_matcher_closeknit.xlsx`** (720 rows, 12 subscribers) — a **close-knit**
  dataset: overlapping six-member community contacts establish the mode without
  ubiquitous hubs; each reviewed ordinary pair has one rarer shared contact and
  rates Medium, while members 11+12 have 3 rare private mutuals and rate High.

Every expected outcome below was verified by running the generated rows through the
real engine (`app.matching.service.compute_match`) before the workbooks were written
(generator: `tools/gen_matcher_scenarios.py`; rerun it after any threshold change —
it fails if the tables drift from the engine). Import a file, open the Spreadsheet
screen's **Contact matcher** card, and compare each pair against its row. The card
also shows the **dataset-mode line** (strangers vs close-knit, with a
High/Medium/Low classification confidence, or "near tie" on the boundary) and
**≈ near-boundary notes** when a gate value sits close to a tier line.

Pair members share a phone prefix: `555PP01` vs `555PP02` where `PP` is the
scenario number (compare `5550101` with `5550102`, and so on).

| Pair | Phones | Expected findings (strength [bound by]) |
|------|--------------------|------------------------------------------|
| P01 | 5550101 / 5550102 | Direct **High** (both directions, 8 calls + 4 SMS); Mutual **High**; Meeting up **High** (6 events) — the everything-pair |
| P02 | 5550201 / 5550202 | Direct **High** only — heavy callers who share nothing else (the spec's "never absurdly Low" case) |
| P03 | 5550301 / 5550302 | Direct **Medium**, direction "A → B only" |
| P04 | 5550401 / 5550402 | Direct **Low** (2 records), direction "B → A only" |
| P05 | 5550501 / 5550502 | Mutual **High** only — 5 distinctive shared contacts, all gates High |
| P06 | 5550601 / 5550602 | Mutual **Medium** [overlap share] — 3 shared of 10-contact circles (30%) |
| P07 | 5550701 / 5550702 | Mutual **Low** [distinctiveness] — 7 shared but 5 are dataset-common hubs (2/7 distinctive) |
| P08 | 5550801 / 5550802 | **No link** — shared contacts exist but only 1 is distinctive, below the 2-contact floor: the pizza-place discount suppressing the finding entirely |
| P09 | 5550901 / 5550902 | Meeting up **High** only — 6 meet-up days in a private park |
| P10 | 5551001 / 5551002 | Meeting up **Medium** [event count] — 3 events |
| P11 | 5551101 / 5551102 | Meeting up **Low** [location distinctiveness] — 5 meet-ups, all in the dataset-common MALL |
| P12 | 5551201 / 5551202 | Mutual **Low** [sample] AND Meeting up **Low** [sample] — the second subscriber has only 10 records, capping strong evidence |
| P13 | 5551301 / 5551302 | Mutual **Low** [window overlap] + **caveat** — A observed May 1–14, B May 16–30 (0% window overlap) |
| P14 | 5551401 / 5551402 | **No link** — nothing shared in any dimension |
| P15 | 5551501 / 5551502 | **No link**, but the "shared areas without time overlap" detail lists P15_STADIUM — both frequent it, always ~6h apart |

## Close-knit dataset pairs — `sample_matcher_closeknit.xlsx`

| Pair | Phones | Expected findings |
|------|--------------------|------------------------------------------|
| CK-ordinary | 4440001 / 4440002 | Mutual **Medium** [distinctiveness] — 5 six-member fabric contacts + 1 pair-specific mutual |
| CK-cross | 4440003 / 4440007 | Mutual **Medium** [distinctiveness] — 4 bridge contacts + 1 pair-specific mutual across the two circles |
| CK-standout | 4440011 / 4440012 | Mutual **High** — 5 six-member fabric contacts + **3 rare private mutuals** (4446011–13) |

The dataset-mode line should read **close-knit — Medium confidence (avg 3.26
non-hub shared contacts per pair)**. No contact used by more than half the 12
subscribers contributes to that mode reading.

## Isolated method-hardening scenarios

These dataset-level checks run in memory through the real engine before either
workbook is written. They cannot all coexist in one import: the small-N case must
have exactly 5 subscribers, while the hub case needs 100.

| Scenario | Population / records | Required outcome |
|----------|----------------------|------------------|
| hub-flip | 100 unrelated subscribers sharing 3 services | **Strangers** mode; no mutual finding from hubs alone |
| double-sided-direct | 5 physical interactions stored as 10 mirrored CDR legs | Direct total **5**, 4 calls + 1 SMS, **Medium**, A→B only |
| location-heavy-sample | 2 contact rows + 48 location-only rows per side | Mutual sample **Low**; location pings do not clear N |
| even-median-spread | shared-contact spreads `[2, 2, 100, 100]` | True median **51**; the k=100 hubs do not inflate mode density |
| small-N-cap | 5 subscribers; otherwise all-High mutual evidence | Mutual **Medium** [comparison population] |
| midnight-straddle | 4 hits around midnight in one continuous session | Exactly **1** event; representative times are one actual matched pair |
| two-meetings-one-day | morning and evening hits in the same area/day | Exactly **2** temporal sessions |

### Threshold recalibration status

The new bases were reviewed against the regenerated scenarios. `DIRECT_HIGH /
DIRECT_MEDIUM = 10 / 3` remains a proposal: 5 physical interactions (10 mirrored
rows) now correctly rates Medium, while the 12-interaction fixture pairs remain
High. `N_HIGH / N_MEDIUM = 50 / 15` also remains a proposal on the stricter
finding-relevant populations: 10 relevant rows stays Low, 15 is Medium, and the
well-sampled fixture pairs still clear 50. These values are retained for
co-founder/domain ratification, not silently treated as final constants.

## How the datasets are constructed

- **Distinctive** shared contacts (`777…` numbers) and meet-up areas (`P##_…`) are
  touched only by their scenario's pair → 0 other subscribers, always distinctive.
- **Common** items: hubs `8880001–8880005` and area `MALL` are used by 10 filler
  subscribers (`5559901–5559910`). With 40 subscribers, the common cutoff for any
  pair is ≥ 20% of the other 38 = **7.6 → 8 subscribers**, so 10 clears it (and
  the `COMMON_MIN_USERS=3` floor is far exceeded — this file exercises the
  percentage arm of the rule; the floor's tiny-population arm is covered by
  `tests/phase2a/test_matching.py`).
- Subscribers meant to pass the mutual sample gate carry ≥ 50 contact-bearing
  rows; co-presence uses located rows. The P12 thin side has exactly 10 relevant
  rows (< `N_MEDIUM` 15). All spans cover May 1–30 except P13's disjoint halves.
- Meet-up hits are 30 minutes apart and sessionized per area with a 60-minute
  maximum gap. P15's stadium visits are hours apart and remain a detail only.
- In the close-knit file, 14 fabric/bridge contacts are each called by exactly 6
  members (the 50% hub ceiling is inclusive). Pair-specific contacts have spread
  2, below the dataset's median shared spread of 6, so they are distinctive.

Generator: `tools/gen_matcher_scenarios.py`. It validates every row with
`app.datasets.validation.validate_row` and asserts the full expectation tables
against `compute_match` before writing the workbooks, so the files and this doc
cannot drift from the engine without failing regeneration.
