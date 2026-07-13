# Pair record ledger

**Date:** 2026-07-13 · **Status:** approved by Khaled (this branch) ·
**Replaces:** the reverted "evidence counters" (commit `3cdac0a`) ·
**Related:** 2026-07-12-contact-matcher-design.md, 2026-07-13-adaptive-matcher-gates.md

## Problem

The matcher answers "is there a link, and how strong?" It cannot answer "**show me the actual
records**". An analyst who wants to read the calls themselves — dates, times, durations, which
side made them — has nowhere to go: the finding evidence tables are digests (top 5 contacts, 8
events, capped at 20 rows), and the export's evidence cell is a one-cell summary.

A first attempt shipped *summary counts* and was rejected: a count is not what was asked for, and
lumping common contacts under the heading "evidence" is wrong — a number half the dataset calls is
not evidence of a link between two people.

## Design

A **separate feature** — not part of the matcher card, not called "evidence". It behaves like the
frequency counter: run it on a pair, read the table, click **Save to export**; saved ledgers
accumulate and fill their own workbook sheet.

### What a ledger is

Every individual CDR record that links the two targets, one row each, in four categories:

| Category | Which records |
|---|---|
| `direct` | records between the pair themselves (either side's rows) |
| `shared_contact` | records from EITHER side to a contact they both have (both sides listed, so you see A's call to `7770101` *and* B's) |
| `meet_up_location` | records of either side in a shared area where a co-presence event happened |
| `shared_location` | records of either side in a shared area with NO co-presence (both frequent it, at different times) |

Per row: category, who (the target), timestamp, call type, duration, other party, area, and two
flags — **distinctive vs common** (for shared contacts/areas) and **"also a target"**.

**Naming (Khaled):** phone numbers resolve to target names wherever the dataset has a target for
them. On `direct` rows both parties are targets, so both are named. On `shared_contact` rows, a
shared contact who is **themselves a target** is flagged (`also_a_target`) and named — an analyst
should immediately see when the third party is someone else under investigation.

**Common items are listed, clearly labeled** — never silently dropped (an analyst must be able to
audit what the matcher discounted) and never presented as evidence.

### Data flow — a separate FEATURE, inside the matching domain

The ledger is its own feature (own card, own endpoints, own save button, own sheet) but it lives
at **`app/matching/ledger.py`**, not in a new `app/ledger/` package. Rationale, since this was a
real decision: the ledger needs the matcher's shared-contact tallies, co-presence events,
commonality counts, and — critically — the SAME distinctive/common classification
(`gates.classify_shared_contacts`, extracted for this). A separate package would have to either
import `app.matching` (breaking the CI-enforced domain-independence contract, or forcing a second
exception on top of `app.reporting`'s) or re-implement that SQL and let its labels drift from the
verdicts they must agree with. Same domain (pair analysis), different output (records, not
verdicts) — which is exactly CLAUDE.md's "new endpoint in an existing domain" case.

`app.matching.ledger` joins the service tier of the import-linter layers contract.

New repo functions: `shared_record_rows` (the four categories' raw records) and the saved-ledger
CRUD. Routes on the matching blueprint:

- `POST /api/ledger` — run for a pair, return the rows (pure read, unaudited, like `/api/match`).
- `POST /api/ledger/save` — **recompute server-side** and persist (nothing client-authored enters
  a report), audited `LEDGER_SAVE`.
- `GET`/`DELETE /api/ledger/saved` — list / remove staged ledgers (audited `LEDGER_DELETE`).

Saved ledgers **accumulate** (like tallies, unlike pair matches, which replace on the same pair):
the same pair may be saved more than once, so the row carries its own id. Migration **3** adds
`saved_ledgers` (id, dataset_id, target_a_id, target_b_id, created_at, rows_json, row_count).

### UI

A new **"Pair record ledger"** card on the Spreadsheet screen (fifth card), styled as a record
listing, NOT an inference: no strength pills, no gates — it reports records, it does not judge them.

- Two target pickers + **Run** → a table of the first **50** rows, with a category filter.
- If there are more than 50, an **Expand** button opens the full grid — scrollable, sorted by
  timestamp, like the records sheet in the Spreadsheet tab — with a row count.
- **Save to export** stages the ledger (full row set, not just the shown 50).

### Excel

A new **"Pair records"** sheet: **fully exhaustive** — every row of every saved ledger, no cap.
Columns: `Ledger ID | Dataset | Pair | Saved at | Category | Who | Phone | Date & time | Call type
| Duration (s) | Other party | Other party name | Also a target | Area | Distinctive`.
Always present; placeholder row when nothing is saved.

### Testing

- `service` unit tests over a fixture dataset: every category present, both sides' records listed,
  common items included and labeled, a shared contact that is also a target flagged and named,
  ordering by timestamp, and A↔B symmetry (canonical pair order, like the matcher).
- Route tests: run/save/list/delete, audit rows, cascade on target delete, recompute-on-save.
- Export test: exhaustive rows (a ledger larger than the UI's 50-row cap exports all rows),
  headers, placeholder.
- `components.test.mjs`: the table renders, the 50-row cap + Expand, no strength pill anywhere.

## Out of scope

No gates, no ratings, no confidence anywhere in this feature. No cross-pair ledger (one pair at a
time). The reverted summary counters are NOT coming back — if a total is ever wanted, it is a
column in a future sheet, not a "count of evidence".
