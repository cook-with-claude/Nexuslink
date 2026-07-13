# Contact-matcher test datasets

Two synthetic CDR datasets (May 2026) that together exercise **every outcome the
contact matcher can produce** — one per dataset mode (adaptive gates, spec
2026-07-13):

- **`sample_matcher_scenarios.xlsx`** (1716 rows, 40 subscribers) — a **strangers**
  dataset: pairs P01–P15 cover each finding type at every strength, every gate as
  the binding (weakest) gate, the common-contact/common-area discount, the
  disjoint-window caveat, the shared-area detail row, and no-link.
- **`sample_matcher_closeknit.xlsx`** (674 rows, 12 subscribers) — a **close-knit**
  dataset: everyone shares the same 8 community contacts, so *any* pair rates
  Medium (real mutuals, group-wide fabric — where the old fixed cutoff would have
  said "no link"); members 11+12 share 3 rare private mutuals and rate High.

Every expected outcome below was verified by running the generated rows through the
real engine (`app.matching.service.compute_match`) before the workbooks were written
(generator: `tools/gen_matcher_scenarios.py`; rerun it after any threshold change —
it fails if the tables drift from the engine). Import a file, open the Spreadsheet
screen's **Contact matcher** card, and compare each pair against its row. The card
also shows the **dataset-mode line** (strangers vs close-knit, with a
High/Medium/Low classification confidence, or "near tie" on the boundary), the
**evidence strip** (raw tallies: direct records, mutual calls, mutual locations
split meet-up / shared-only — no confidence, a count is not a verdict), and
**≈ near-boundary notes** when a gate value sits close to a tier line.

Worth comparing on purpose: **P01** (all three findings) has 12 direct records, 5
shared contacts and 1 meet-up area; **P15** (no findings at all) still counts 1
**shared-only** location — the pair frequents P15_STADIUM hours apart. That is the
counter's whole point: evidence exists even where no verdict fires.

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
| CK-ordinary | 4440001 / 4440002 | Mutual **Medium** [distinctiveness] — 8 shared contacts, all group fabric |
| CK-cross | 4440003 / 4440007 | Mutual **Medium** [distinctiveness] — any clique pair reads the same way |
| CK-standout | 4440011 / 4440012 | Mutual **High** — 8 fabric + **3 rare private mutuals** (4446001–03) |

The dataset-mode line should read **close-knit — High confidence (avg ≈ 8 shared
contacts per pair)**. Import the strangers file next to it and compare: same
"everyone shares contacts" evidence, opposite rules, both explained on screen.

## How the datasets are constructed

- **Distinctive** shared contacts (`777…` numbers) and meet-up areas (`P##_…`) are
  touched only by their scenario's pair → 0 other subscribers, always distinctive.
- **Common** items: hubs `8880001–8880005` and area `MALL` are used by 10 filler
  subscribers (`5559901–5559910`). With 40 subscribers, the common cutoff for any
  pair is ≥ 20% of the other 38 = **7.6 → 8 subscribers**, so 10 clears it (and
  the `COMMON_MIN_USERS=3` floor is far exceeded — this file exercises the
  percentage arm of the rule; the floor's tiny-population arm is covered by
  `tests/phase2a/test_matching.py`).
- Subscribers meant to pass the sample gate carry ≥ 50 records (`N_HIGH`); the
  P12 thin side has exactly 10 (< `N_MEDIUM` 15). All spans cover May 1–30 except
  P13's deliberately disjoint halves.
- Meet-up events are one per (area, day), 30 minutes apart — inside the 60-minute
  inclusive pairing window; P15's stadium visits are hours apart, outside it.
- In the close-knit file, the 8 fabric contacts are called by all 12 members
  (spread 12 = the dataset's median shared spread → not rare), while `4446001–03`
  are called only by members 11+12 (spread 2 → rare).

Generator: `tools/gen_matcher_scenarios.py`. It validates every row with
`app.datasets.validation.validate_row` and asserts the full expectation tables
against `compute_match` before writing the workbooks, so the files and this doc
cannot drift from the engine without failing regeneration.
