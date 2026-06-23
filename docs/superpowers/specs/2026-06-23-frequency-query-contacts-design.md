# Design — Frequency query: locations (%) + ranked contacts

**Date:** 2026-06-23
**Branch:** `frequency-branch` (off `branched-out-dih`)
**Author:** Claude (with Khaled)

## Goal

Extend the "frequent" query in `phase1_cdr/` so it reports two things for a
subject user:

1. **Frequent locations** — the subject's top-5 areas, shown with each area's
   **percentage** (share of the subject's calls). Logic already exists
   (`detect_frequent_areas` returns `(area, count, share)`); only the
   presentation and the `top_n` default change.
2. **Frequent contacts (new)** — the top-5 phone numbers the subject has
   communicated with, ranked by total telecommunications, each broken down
   **4-way by type**: call out (1), call in (2), SMS out (11), SMS in (22).

`top_n` defaults to **5** for both and is a function parameter, so a later UI
can request more.

## Scope boundary (per Khaled)

Every query is **single-subject**: a detector looks only at the subject user's
own rows. The other party's data is carried for realism/consistency and is used
by exactly one thing — the contacts ranking, which is keyed on the counterparty
*number* only. `other_imei` / `other_area` are stored but **read by no query yet**.

## Schema change

The CDR schema grows from 6 to 9 columns. `loader.py` `REQUIRED_COLUMNS` gains:

| Column | Meaning | dtype |
|---|---|---|
| `other_party` | the number the subject communicated with | string |
| `other_imei` | that party's device | string |
| `other_area` | that party's location | (string, default) |

`other_party` and `other_imei` join `_STRING_COLUMNS` so leading zeros survive.
Existing detectors (`detect_home` / `detect_work` / `detect_frequent_*`) do not
read the new columns and are behaviourally unchanged. The team's real generator
must emit these 9 columns.

## detection.py

New dataclass:

```python
@dataclass
class ContactRank:
    number: str
    total: int       # ranking key
    call_out: int    # call_type 1
    call_in: int     # call_type 2
    sms_out: int     # call_type 11
    sms_in: int      # call_type 22
```

New pure function `detect_frequent_contacts(df, top_n=5) -> List[ContactRank]`:
group the subject's rows by `other_party`; per contact compute `total` plus the
four per-`call_type` counts; sort by `total` desc, then earliest `timestamp`
asc, then `number` asc (same deterministic tie-break as `_sorted_areas`); return
the top `top_n`. Empty frame → `[]`. No confidence gates — this is a raw
frequency ranking, not an inference (same as `detect_frequent_areas`).

`detect_frequent_areas` default `top_n` changes `3 → 5`.

## Fixtures & independent ground truth (dev_fixtures.py)

Each generated record gains a counterparty. Each user gets a fixed
**contact pool** — a few `(number, imei, area, weight)` identities with clearly
separated weights so the top-5 ranking has no ties and is reproducible. A
contact keeps the same imei/area across all its rows (consistency).

**RNG isolation (critical):** contact assignment draws from a *separate*
`random.Random` instance so the existing main RNG stream (dates, hours,
call_types, areas) is byte-identical to before. This guarantees the current
home/work/frequent/confidence ground truth and the verified 12/12 + 13-passed
state are unchanged; only the new contacts data is added.

Ground truth stays independently tallied (plain `groupby`, never importing
`detection.py`): a new `_contacts(user_df, top_n=5)` helper mirrors the
detector's grouping/tie-break and emits each user's expected ranked contacts
with the four type-counts. `ground_truth.json` gains a `contacts` block per user.

## Harness, tests, docs

- `validate.py` — new `_check_contacts()` compares the detector's ordered list
  (numbers + four counts) against the spec exactly. `main.py` prints contacts as
  a second table; the locations display gains a `%`.
- `tests/test_detection.py` — new unit tests for `detect_frequent_contacts`
  (rank order, 4-way bucketing, tie-break, `top_n` cap); update the `_df` helper
  to include the 3 new columns.
- `README.md` — document the 9-column schema and the expanded frequency query.
- Harness check count rises ~12 → ~17 (one `contacts` row per user).

## Out of scope

No UI, no use of `other_imei` / `other_area` in any query, no change to the
four-gate confidence model or to home/work detection.
