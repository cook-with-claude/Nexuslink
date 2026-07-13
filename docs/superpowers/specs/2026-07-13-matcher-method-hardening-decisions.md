# Contact Matcher — Method Hardening Decisions

- **Date:** 2026-07-13
- **Status:** Decisions ACCEPTED by Nadim (2026-07-13). New threshold *values* below are
  proposals pending co-founder/domain ratification (same protocol as the Phase-1 gates and
  the existing matcher thresholds). Method *directions* are settled.
- **Branch:** `claude/contact-matcher` (Nadim merges). This memo drives a follow-up
  method-hardening pass on the same branch, AFTER the mechanical "Bucket A" bug fixes land.
- **Source:** dual independent review (Claude Code terminal pass + Codex fresh-eyes pass),
  2026-07-13. Findings that were purely mechanical are handled separately (Bucket A) and are
  not repeated here. This memo covers only the changes that alter what the matcher *claims*.
- **Scope guard:** synthetic-data portfolio project, but datasets can get large — the two
  scalability items ARE in scope (accepted), not deferred. Phase 1 stays frozen; every fix is
  in `app/matching/`, `app/reporting/`, `app/infra/migrations.py`, and the fixtures/docs.

## Why these matter

Every item below changes a rating, a count, or the dataset the ratings reason about. The
guiding principle is the project's framing invariant: the matcher makes *gated, conservative
claims about people*. A **false positive** (asserting a link that isn't there) is the worst
failure; a false negative (missing a weak real link) is acceptable. The items are ordered by
that lens.

---

## 1. Hub conflation inflates "close-knit" mode — FALSE POSITIVE — **merge blocker**

**Where:** `app/matching/repo.py:185` (`dataset_interconnectedness`, `_SHARED_SPREAD`) →
`app/matching/gates.py:228` (close-knit branch of `_mutual_finding`).

**Problem.** `dataset_density` sums `C(k, 2)` over *every* contact, where `k` = subscribers
who contacted that party. Ubiquitous hubs (service numbers, voicemail, one popular shop)
dominate the sum. So a dataset of unrelated people who merely share a few service numbers is
mislabeled **close-knit**, and in close-knit mode the mutual finding *always fires*.

**Reproduced (Codex).** 100 unrelated subscribers each calling the same 3 service numbers →
D ≈ 3.0 ≥ `CLOSE_KNIT_BOUNDARY=2.0` → close-knit → any well-sampled pair gets a **Medium
"Mutual relationship"** for sharing nothing but hubs.

**Decision — ACCEPTED.** Strip ubiquitous hubs from the interconnectedness metric *and* stop
the close-knit mutual finding from firing on hubs alone.
- Add a ubiquity ceiling to `_SHARED_SPREAD`: a contact counts toward interconnectedness only
  when it is shared by `>= 2` **and** `<= HUB_CEILING` subscribers, where
  `HUB_CEILING = round(HUB_UBIQUITY_FRACTION * n)` over the dataset's distinct subscribers.
  Proposal: `HUB_UBIQUITY_FRACTION = 0.50` (a contact used by more than half the dataset is a
  hub, not social fabric). *Threshold to ratify.*
- The close-knit mutual finding must require `len(distinctive) >= 1` before it fires (a purely
  hub-based overlap is not a relationship). Today close-knit "always fires" on raw shared
  count; gate that on at least one distinctive shared contact.
- The distinctiveness classifier already discounts hubs for *rating*; this change makes the
  same discount govern *mode selection* and *whether the finding exists at all*, so the three
  can't disagree.

**Ripple.** Changes `dataset_context.mode` on hub-heavy datasets and can suppress the mutual
finding for hub-only pairs. `sample_matcher_scenarios.xlsx` / `_closeknit.xlsx` expectations
must be regenerated; add a dedicated hub-flip scenario (below).

**Test to add.** "N strangers sharing only service numbers stay in strangers mode and yield no
mutual finding" — the exact repro above, asserted against the real engine.

---

## 2. Direct volume double-counts mirrored call legs — inflates strength — **high**

**Where:** `app/matching/repo.py:70` (`direct_contact`).

**Problem.** Counts every row where A↔B. If the dataset stores *both* legs of a call (A's
outgoing row + B's incoming row), each real interaction is counted twice. The docstring itself
notes "a dataset may carry one side or both" — the ambiguity is known and unhandled.

**Reproduced (Codex).** 5 physical A→B calls stored as 5 A-out + 5 B-in rows → volume 10 →
**High** (`DIRECT_HIGH=10`) instead of Medium.

**Decision — ACCEPTED.** This is first a **data-contract decision**, then a code fix.
- **Contract:** declare the canonical CDR single-sided vs double-sided. Recommended:
  treat the store as *possibly* double-sided and dedupe at read time (robust regardless of how
  a real export arrives), rather than trusting the importer to normalize.
- **Fix:** in `direct_contact` (and `direct_contact_records` for the ledger), collapse mirrored
  legs — group by `(timestamp, frozenset({phone_number, other_party}), modality)` where
  modality ∈ {call, sms}, counting each unique interaction once. Keep the direction split
  (`a_to_b`/`b_to_a`) derived from whichever leg(s) are present.
- Re-examine `DIRECT_HIGH / DIRECT_MEDIUM` (10/3) once counts are halved for double-sided data.
  *Thresholds to re-ratify.*

**Ripple.** Changes direct-volume counts and the ledger's `direct` rows for double-sided
datasets. Regenerate fixtures; the generator should emit at least one double-sided pair so the
dedup is exercised end-to-end.

---

## 3. Sample gate counts location pings, not relevant records — over-credits — **high**

**Where:** `app/matching/repo.py:25` (`record_count`) → `app/matching/gates.py:252, 301`
(`sample = min(n_a, n_b)`).

**Problem.** The confidence gate uses each side's *total* row count — calls, SMS, and
location-only pings alike. A target with 48 location rows + 1 call to each of 2 shared contacts
scores N=50 → **sample: High**, off 2 relevant records.

**Decision — ACCEPTED.** Make the sample gate count records *relevant to the finding*.
- **Mutual finding:** sample = `min` over the two sides of the count of **contact records**
  (rows with `other_party IS NOT NULL`), not all rows. Add a repo fact
  `contact_record_count(conn, dataset_id, phone)`.
- **Co-presence finding:** sample = `min` over sides of the count of **located records** (rows
  with a non-null `area`), which is the population the meet-up inference actually draws on.
- Keep `N_HIGH / N_MEDIUM = 50/15` for now but flag them for re-ratification, since the
  denominator shrinks and the same numbers are now stricter. *Thresholds to re-ratify.*

**Ripple.** Lowers `sample` ratings on location-heavy targets; some findings drop a tier.
Regenerate fixtures; add a "location-heavy target, few contact records" scenario.

---

## 4. "Median" is the lower-middle value, not a real median — biases suppression — **medium**

**Where:** `app/matching/repo.py:203` (`dataset_interconnectedness`,
`contact_spread_median`).

**Problem.** For an even number of shared contacts, `LIMIT 1 OFFSET (parties-1)//2` returns the
lower of the two middle order statistics, not the median. On `[2, 2, 100, 100]` it reports **2**
(true median 51). The close-knit rarity test `commonality + 2 < median` then can't ever flag a
contact as rare when the base collapses to 2 → genuine pair-private mutuals get downgraded
(High → Medium).

**Decision — ACCEPTED.** Compute a genuine median.
- The shared-contact `k` list is small (bounded by the count of shared contacts); fetch it and
  use `statistics.median` in Python (average of the two middle values for even cardinality),
  or the SQL equivalent averaging the two central order stats. Keep the `>= 2` shared-only
  base restriction.
- This is a definitional correctness fix; the *concept* (typical shared-contact spread as the
  rarity base) is unchanged, so no new user-facing threshold — but confirm the direction with
  a domain eye, since a truer (higher) median makes "rare" easier to reach.

**Ripple.** Shifts some close-knit distinctiveness ratings upward. Regenerate fixtures; add an
even-cardinality spread scenario asserting the true median.

---

## 5. Commonality floor makes "common" impossible in tiny datasets — small-N FP — **medium**

**Where:** `app/matching/gates.py:120` (`_is_common`, `COMMON_MIN_USERS`) →
`build_findings` small-population caveat at `gates.py:346`.

**Problem.** `_is_common` requires `users_with >= max(COMMON_MIN_USERS=3, 0.2·others)`. In a
5-subscriber dataset (others = 3 for a pair), a contact used by 2 of 3 others — 67% of the
comparison population — is *not* common, so it reads distinctive and can drive a **High**
finding. The `SMALL_POPULATION` caveat is advisory and does not cap the rating.

**Decision — ACCEPTED.** Cap the rating, don't just caveat it.
- When `other_users < SMALL_POPULATION` (=10), cap the mutual and co-presence finding strength
  at **Medium** regardless of the gates, and keep the existing caveat text. Rationale: below
  that population the commonality math is too crude to justify a High claim in either
  direction — this bounds the false-positive without re-introducing the "one coincidental
  caller deletes evidence" failure that `COMMON_MIN_USERS` was added to prevent.
- `COMMON_MIN_USERS=3` and `SMALL_POPULATION=10` unchanged. *Confirm the cap tier (Medium).*

**Ripple.** Caps a handful of small-dataset findings at Medium. Regenerate fixtures; add a
5-subscriber scenario that would score High un-capped and asserts the Medium cap.

---

## 6. Co-presence dedups by calendar day, not session — mis-counts events — **medium**

**Where:** `app/matching/repo.py:98` (`co_presence_events`, `GROUP BY ... substr(day)`).
Also fixes the related evidence-time issue: `MIN(a_time)` / `MIN(b_time)` are taken
independently after the group, so the displayed pair can be > the 60-minute window apart.

**Problem.** Collapsing per `(area, calendar day)` mis-counts two ways: a single meeting across
midnight becomes 2 events (can clear `EVENTS_MEDIUM=2`); two genuine morning/evening meetings
in the same area on one day collapse to 1. Canonicalization fixed A↔B symmetry, not this.

**Decision — ACCEPTED.** Dedup by **temporal session**, not calendar day.
- Gather the co-presence hits (the matched (a_time, b_time) pairs per area), sort by time, and
  start a new session when the gap since the previous hit exceeds `SESSION_GAP_SECONDS`.
  Proposal: `SESSION_GAP_SECONDS = 3600` (reuse the co-presence window as the session gap).
  *Threshold to ratify.*
- Do the sessionization in Python over the joined hits (or a windowed SQL pass), not a
  `substr(timestamp,1,10)` bucket. This removes the midnight artifact and separates distinct
  same-day meetings.
- While here, report each event's representative times from the **actual closest matched
  pair** in that session, not independent `MIN`s — so the shown a_time/b_time always satisfy
  the window (pairs with my terminal-review finding on misleading event times, and with
  Bucket A's #11 which surfaces a_time/b_time in the UI).

**Ripple.** Changes event counts on midnight-straddling / multi-meeting datasets. Regenerate
fixtures; add a midnight-straddle scenario and a two-meetings-one-day scenario.

---

## 7. Co-presence self-join is O(A×B) — scalability — **ACCEPTED (in scope)**

**Where:** `app/matching/repo.py:98` (self-join), plus the unindexed `GROUP BY other_party` /
`GROUP BY area` scans in `dataset_interconnectedness` and `_commonality`.

**Problem.** The self-join filters time *after* joining and can only use
`idx_records_dataset_phone`; at 50k rows/side in one area it is up to billions of comparisons.
`dataset_interconnectedness` re-runs its full-scan `GROUP BY` ~3× per request with no caching.

**Decision — ACCEPTED.** Index + memoize.
- New **migration 4**: add composite indexes
  `idx_records_dataset_other_party (dataset_id, other_party)`,
  `idx_records_dataset_area (dataset_id, area)`,
  `idx_records_dataset_area_time (dataset_id, area, timestamp)`.
  Appended to `MIGRATIONS` per the ADR-0002 seam; runs on next login. Low risk, no query
  rewrites needed — the group-bys and the self-join become index range ops.
- Memoize `dataset_interconnectedness` per `dataset_id` for the life of a request (it is a
  pure dataset fact, unchanged between the `/match` and `/ledger` calls of one comparison), so
  it is computed once, not ~3× per endpoint and again for the ledger.
- If profiling still shows the self-join dominating on large data, bucket both sides into
  `(area, hour)` keys in one pass and match buckets in Python — deferred until measured.

**Ripple.** None to outputs; migration 4 must be covered by the migrate-on-login tests.

---

## 8. Unbounded ledger rows — Excel overflow / memory — **ACCEPTED (in scope)**

**Where:** `app/matching/routes.py:138` (store `rows_json`),
`app/reporting/routes.py:51` + `app/reporting/export.py:256` (decode + materialize).

**Problem.** No cap on stored `rows_json` or the exported "Pair records" sheet. Ledgers
accumulate; enough saved rows exceed Excel's ~1,048,575 data-row limit and fail the whole
export, with memory pressure plausible earlier. (Already flagged by Khaled as an open question
in HANDOFF.)

**Decision — ACCEPTED.** Cap with disclosure — consistent with the feature's transparency rule.
- Cap the stored/exported ledger at `LEDGER_ROW_CAP` rows (proposal: `50_000` per saved
  ledger — well clear of Excel's limit even across several saved ledgers, and far past any
  real analyst listing). *Threshold to ratify.*
- When a ledger is truncated, store and surface an explicit note ("N of M rows shown; listing
  capped") in the payload, the card, and the export sheet — never a silent truncation.
- Use openpyxl write-only / streaming for the "Pair records" sheet so a large workbook does not
  materialize entirely in memory.
- Guard the total exported row budget across *all* saved ledgers so one workbook can never
  cross Excel's hard limit; if the aggregate would exceed it, cap and note per the same rule.

**Ripple.** New cap path needs tests: a ledger above the cap is truncated-with-note; the export
of many large ledgers stays under Excel's limit.

---

## Cross-cutting: the fixture/generator ripple (do this once, last)

Items 1–6 change engine outputs, so after implementing them:
1. Update expected-outcome tables in `docs/matcher-test-scenarios.md`.
2. Add the new scenarios named above to `tools/gen_matcher_scenarios.py`
   (hub-flip, double-sided direct, location-heavy sample, even-median spread, small-N cap,
   midnight-straddle, two-meetings-one-day).
3. Regenerate `sample_matcher_scenarios.xlsx` + `sample_matcher_closeknit.xlsx` via the
   generator — it asserts every expectation against the *real* `compute_match` before writing,
   so a stale table or drifted engine fails regeneration (this is the safety net; keep it).
4. Update `tests/phase2a/test_matching.py` expectations that these method changes move, and add
   the new-scenario assertions and the migration-4 test.

## Suggested sequencing

Land after Bucket A (mechanical bugs) is merged, in this order — earlier items change the
datasets later items are tested against:

1. **#7 indexes (migration 4)** — pure infra, no output change; unblocks the rest cheaply.
2. **#1 hub conflation** — the blocker; also changes the fixtures most.
3. **#2 direct-leg dedup**, **#3 sample base**, **#4 true median** — independent rating fixes.
4. **#6 session dedup** — includes the representative-time fix.
5. **#5 small-N cap** — a final clamp over the above.
6. **#8 ledger cap + streaming** — self-contained; can run in parallel with any of the above.
7. **Fixture/generator regeneration + test updates** — once, at the end.

## Open threshold values to ratify (co-founder/domain)

`HUB_UBIQUITY_FRACTION` (0.50) · revisit `DIRECT_HIGH/MEDIUM` (10/3) · revisit `N_HIGH/MEDIUM`
(50/15) against the new relevant-record base · small-N cap tier (Medium) · `SESSION_GAP_SECONDS`
(3600) · `LEDGER_ROW_CAP` (50,000). Everything else is a definitional/correctness fix with no
new user-facing knob.
