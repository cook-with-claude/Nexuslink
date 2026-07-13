# Contact Matcher + Saved Exports — Design

- **Date:** 2026-07-12
- **Status:** Approved by Khaled (brainstorm 2026-07-12); thresholds pending Nadim/domain review
- **Branch:** `claude/contact-matcher` (Nadim merges)
- **Scope:** Phase-2-line feature on the Spreadsheet tab. Does not touch `phase1_cdr/` (frozen)
  and does not depend on Phase 3 increments beyond migrate-on-login (3.1, already merged).

## 1. What it is

Two features that share a data model and an export surface:

1. **Contact matcher** — a fourth card on the Spreadsheet tab. Pick two different targets from
   the same dataset, click **Compare**, and get a list of typed relationship **findings**, each
   with a plain-words label, a High/Medium/Low strength, headline numbers, and expandable
   evidence. Nothing about a run is stored until the user clicks **Save to export**.
2. **Saved exports** — both matcher results and Frequency-explorer tallies become savable via an
   explicit **Save to export** click, land in two new sheets of the existing single export
   workbook, and are curatable (list + remove) from the Export screen.

**Framing rule (project invariant):** the matcher is an *inference* — it produces gated,
confidence-rated claims, styled like the Detection card. The explorer stays a plain count. The
two must never blur.

## 2. Findings model (the heart of the feature)

A comparison returns **0..n findings**. Multiple findings coexist; there is no single blended
"relationship score". Each finding: `{type, label, strength, headline, evidence, bound_by}`.

| Type | Label | Fires when | Headline example |
|---|---|---|---|
| `direct_contact` | "Direct contact" | ≥ 1 record where one target's `other_party` is the other target | "Direct contact — 40× (32 calls, 8 SMS, both directions)" |
| `mutual_contacts` | "Mutual relationship" | ≥ 2 *distinctive* shared contacts | "Mutual relationship — 12 shared contacts (58% of A's circle, 71% of B's)" |
| `co_presence` | "Meeting up" | ≥ 1 meet-up event | "Possible meet-ups — 9 co-located events across 6 days" |

- **Meet-up event:** both targets have ≥ 1 record in the **same area within 60 minutes** of each
  other. All hits in the same (area, calendar day) collapse into **one** event, so a long call
  session cannot inflate the count.
- **Shared areas without time overlap** are too weak to be a finding: they appear only as a
  detail row inside the expanded evidence ("also share 3 areas without time overlap").
- **No findings** → "No link found between these targets", plus an honesty caveat when the reason
  is structural (observation windows barely overlap, or a target has zero records).
- Every finding records **which gate bound its strength** (`bound_by`), surfaced in UI + export
  (same transparency rule as detection issue #10).

## 3. Gates (per-finding strength, weakest-link)

Strength = `min()` of the gates applicable to that finding type. Gates guard distinct failure
modes; direct contact is positive evidence, so it is its own finding rated by its own volume —
it is **not** folded into a `min()` with doubt gates (that would rate two people who call each
other 40× as "Low" if they share nothing else).

| Gate | Question it guards | High | Medium | Applies to |
|---|---|---|---|---|
| **Sample (N, two-sided)** | enough data on BOTH sides? Uses `min(N_A, N_B)` | ≥ 50 | ≥ 15 | mutual, co-presence |
| **Window overlap** | observed during the same period? overlap ÷ shorter span | ≥ 60% | ≥ 20% | mutual, co-presence |
| **Overlap share** | shared contacts ÷ smaller side's contact circle | ≥ 40% | ≥ 15% | mutual |
| **Distinctiveness** | share of the pair's common contacts/areas that < 20% of *other* users in the dataset also have | ≥ 60% | ≥ 30% | mutual, co-presence (busy-tower discount) |
| **Event count** | enough meet-up events? | ≥ 5 | ≥ 2 | co-presence |
| **Direct volume** | direct interactions count | ≥ 10 | ≥ 3 | direct only |

All thresholds are **named constants in one module, flagged for Nadim/domain review** — same
protocol as the Phase-1 gate thresholds (which went through Nadim + co-founder). N thresholds
reuse the Phase-1 values (50/15).

## 4. Architecture (Approach A — new domain)

New domain package per CLAUDE.md "where does X go":

```
app/matching/
  __init__.py
  repo.py     DOMAIN — SQL over a caller conn; returns dicts; no commit, no flask, no audit
  gates.py    DOMAIN (pure) — thresholds + per-finding rating; no SQL, no flask; unit-testable
  routes.py   APPLICATION — request validation, unit-of-work, audit, response shaping
```

- Blueprint registered in `create_app()`; domain added to the import-linter layer/independence
  contracts and `tests/architecture/` sets.
- `repo.py` queries (all against `cdr_records`, using the existing
  `idx_records_dataset_phone` hot path):
  1. per-target contact tallies (`other_party`, per-side counts, call/SMS split);
  2. direct-contact scan (either target's number as the other's `other_party`, both directions);
  3. per-target (area, timestamp) sets for meet-up pairing;
  4. per-target observation span (min/max timestamp);
  5. dataset-wide commonality: for each shared contact/area, how many *other* phone numbers in
     the dataset also have it (feeds distinctiveness).
- `gates.py` consumes those plain dicts and returns the findings list. No I/O.
- **Explorer save** reuses the existing `analysis.repo.frequency()` result; saving belongs to the
  matching-adjacent "saved exports" surface (see §6 for who owns which table).

## 5. Data model — migration 2 (first real use of the ADR-0002 seam)

Append `(2, ddl)` to `MIGRATIONS` in `app/infra/migrations.py`; runs on next login.

```sql
CREATE TABLE IF NOT EXISTS saved_pair_matches (
  id INTEGER PRIMARY KEY,
  dataset_id INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
  target_a_id INTEGER NOT NULL REFERENCES targets(id) ON DELETE CASCADE,
  target_b_id INTEGER NOT NULL REFERENCES targets(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL,
  result_json TEXT NOT NULL,
  UNIQUE (target_a_id, target_b_id)
);

CREATE TABLE IF NOT EXISTS saved_tallies (
  id INTEGER PRIMARY KEY,
  target_id INTEGER NOT NULL REFERENCES targets(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL,
  filters_json TEXT NOT NULL,
  filter_label TEXT NOT NULL,
  tally_json TEXT NOT NULL
);
```

- Pair identity is **order-normalized** (store `target_a_id < target_b_id`) so A↔B and B↔A are
  the same pair; saving again **replaces** the row (`UNIQUE` + upsert). Tallies accumulate;
  each is individually deletable.
- `result_json` stores the full findings payload **as shown on screen** — export copies stored
  results, never recomputes (existing export contract).
- `docs/reference/schema.md` gains both tables + the migration-2 note.

## 6. API surface

All behind the existing auth/lock gates; mutations audited (`audit_log` event types
`PAIR_MATCH_SAVE`, `PAIR_MATCH_DELETE`, `TALLY_SAVE`, `TALLY_DELETE`; the run itself is a read
and is not audited, matching `frequency`).

| Endpoint | Does | Errors |
|---|---|---|
| `POST /api/match` `{target_a_id, target_b_id}` | run comparison, return findings payload; stores nothing | 404 unknown target; 422 same target twice or different datasets |
| `POST /api/match/save` `{target_a_id, target_b_id}` | recompute the comparison server-side and persist it (replace-on-same-pair). The client never supplies the stored payload — a client-authored result must not be able to enter the report | 404/422 as above |
| `POST /api/frequency/save` `{target_id, filters}` | recompute the tally server-side from the filters and persist it + a human-readable label | 404 unknown target; 422 malformed filters |
| `GET /api/export/saved` | `{pair_matches:[…], tallies:[…]}` for the Export screen list | — |
| `DELETE /api/export/saved/pair/<id>` / `…/tally/<id>` | remove a saved item | 404 |

Routes own the unit-of-work (repo calls → `audit.write_audit` → commit/rollback), per the
architecture invariants. `docs/reference/api.md` documents all five.

**Zero-record target:** `POST /api/match` is a **200 with "no link" + caveat**, not an error —
"target B has no records" is an answer, not a malfunction.

## 7. UI

- **Contact matcher card** (4th card, Spreadsheet tab, below the explorer): dataset picker → two
  target pickers filtered to that dataset (must differ) → **Compare**. Styled in the *inference*
  visual family (like Detection). Results: one row per finding — label, strength pill,
  headline — expandable to evidence tables (shared contacts with per-side counts, meet-up event
  list (area/date/hour), direct-call summary, weak-signal detail rows, and each finding's
  `bound_by` gate). "No link found" + caveat when empty. **Save to export** button on a rendered
  result.
- **Explorer card**: gains **Save to export** under a rendered tally.
- **Export screen**: lists saved pair matches and saved counts with remove buttons; export
  behavior otherwise unchanged (same single workbook, same file-name picker).
- New JS lives in `app/web/js/screens/spreadsheet.js` + `components.js` helpers as fits the
  existing no-build pattern; renderers get `node --test` coverage and `test_ui.py` needles.

## 8. Export workbook

The existing single workbook (`app/analysis/export.py` builder, pure rows→xlsx) gains two sheets,
always present ("none saved" placeholder row when empty), after the existing three:

1. `Summary` *(existing)*
2. `Frequent areas` *(existing)*
3. `Frequent contacts` *(existing)*
4. **`Contact matches`** *(new)* — one block per saved pair: pair header (targets, dataset,
   saved-at), then one row per finding (label, strength, bound-by gate, headline numbers), then
   key evidence rows (top shared contacts with per-side counts; meet-up events; direct summary).
5. **`Frequency counts`** *(new)* — per saved tally: filter label + saved-at header, then the
   value/count rows.

Sheet builders stay pure (fed rows by the route). The export route composes data from
`analysis.repo` and the new saved-items reads; if the import-linter independence contracts
forbid the analysis route importing `matching.repo`, the fallback (decided at plan time, not
here) is a thin APPLICATION-layer reporting module that both domains feed — the workbook layout
above is fixed either way. Findings in the export must read from `result_json` verbatim
(no recompute).

## 9. Testing

- **Gate unit tests** (`gates.py`, pure): a fixture pair per scenario — direct-only,
  mutual-only, meet-up-only, all three, no link, disjoint windows → caveat, busy-tower discount,
  and each gate individually binding the `min()`; threshold boundary values.
- **Repo tests:** meet-up 59-vs-61-minute boundary, same-(area,day) dedup, order-normalized pair
  identity, per-side counts, dataset-commonality query, zero-record target.
- **Migration test:** a v1 database migrates in place to v2 with both tables, data intact;
  fresh DB converges identically.
- **Route tests:** validation (404/422), save-replaces-save, tally accumulate + delete, audit
  events written, lock/auth behavior inherited.
- **Export tests:** five sheets, placeholder rows when nothing saved, saved content matches
  `result_json` byte-for-byte semantics (no recompute).
- **Frontend:** `node --check` all modules, `node --test` for new renderers, `test_ui.py`
  symbol needles updated.
- **Architecture:** import-linter contracts + `tests/architecture/` cover `app/matching/`
  (repo imports infra only; gates import nothing app-level; no cross-domain internals).

## 10. Sequencing (one spec, two reviewable chunks)

1. **Matcher core:** migration 2, `app/matching/` (repo + gates + routes), matcher card,
   `Contact matches` sheet, save/list/delete for pairs.
2. **Saved tallies:** `POST /api/frequency/save`, explorer save button, `Frequency counts`
   sheet, Export-screen tally management.

## 11. Out of scope (explicitly)

- Cross-dataset pairs (API shape doesn't preclude them; validation rejects them for now).
- Any single blended "relationship score" across finding types.
- N-way (3+) comparison, graph/link visualizations.
- Recalibrating thresholds — proposals ship as constants; Nadim/domain review adjusts them.
- Phase-3 multi-user concerns (per-user saved lists etc.) — saved items are account-global,
  like every other table today; Phase 3.2b-2+ owns per-user scoping.
