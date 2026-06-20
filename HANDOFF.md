# Handoff Log

Shared scratchpad between Claude Code and Codex. Newest entries on top.
Each entry: who, what changed (with file:line where useful), what's left, and any
disagreement or open question. See `COLLAB.md` for the protocol.

---

## 2026-06-20 — Claude: re-tuned thresholds + realistic-scale fixtures (branch `branched-out-dih`)

**Context:** the `N_*` / `DENSITY_*` thresholds were placeholders scaled to the
tiny ~28-day, ~20-call-per-window fixtures (the standing open item from both
prior entries). Khaled asked to re-tune them for a realistic dataset (500–5000
calls per user) and actually run the tests. **pandas now loads in `.venv`
(3.0.3) on this machine — the Windows Application Control block from 06-18 is
gone — so pytest + main.py were really executed this time, not just traced.**

**What changed (all on `branched-out-dih`, NOT merged):**
- `detection.py` — **only the count gates retuned** (Share/Closeness are
  scale-invariant ratios, left untouched): `N_HIGH 15→50`, `N_MEDIUM 5→15`,
  `DENSITY_HIGH 0.45→0.40`, `DENSITY_MEDIUM 0.20→0.15`. Calibration comments
  updated; the four-gate architecture is unchanged (`min()` weakest-link kept,
  per Khaled's explicit decision not to change it).
- `dev_fixtures.py` — rebuilt at realistic scale: **5 users, per-user totals
  500–5000, each with a DIFFERENT observation span** so Density discriminates.
  `_add` now takes a per-user date pool. A (~365d, dense → all High), B (~180d,
  near-tie → ≤Medium), C (~21d, ~40 records, no in-window data → Insufficient/
  Low — kept deliberately sparse as the N-floor case, the one user exempt from
  the volume target), D (~180d, adversarial → home ≤Medium / work ≤Low).
- **New User E (`01000005`)** — the open-item Density user: ~30 unanimous Hamra
  overnight calls scattered over a full year + ~570 evening calls. N=Medium,
  Share=High, Closeness=High, **Density=Low (0.074)** → home is `Low`, bound
  SOLELY by Density. Ground truth pins E's home `expected_confidence` EXACTLY to
  `Low` (not a ceiling) so it fails if any gate other than Density caps it.
  Density is no longer dormant in the harness.
- `ground_truth.json` / `sample_data.csv` regenerated (3700 records). Ground
  truth still tallied independently, no `detection.py` import.
- `tests/test_detection.py` — rescaled the 4 unit tests that baked in the old
  numbers (`clear_winner_is_high`→60 recs, `share_gate_caps_thin`→20-rec winner,
  both `density_gate_*` tests recomputed for the new cutoffs via a new
  `_spaced_nights` helper). Ratio/tie-break/frequent tests untouched.
- `README.md` — threshold note rewritten (no longer "placeholders"); user table
  is now 5 users with spans/volumes + an E explainer.

**Verified (actually executed in `.venv`):**
- `pytest tests/` → **11 passed**. `python main.py sample_data.csv
  ground_truth.json` → **11/11**. Per-user gate trace confirms the binding gate
  for each: A all-High; B/D capped by Closeness (near-tie); E capped by Density
  alone (N=Medium, Share/Closeness=High).

**Gate-design notes for the reviewer (Codex/Nadim) — NOT acted on, raised per
Khaled's request; architecture intentionally left as-is:**
1. **Share and Closeness partially overlap.** A dominant winner (high Share)
   mechanically tends to produce a small runner-up ratio (good Closeness), so
   the two gates correlate and `min()` slightly double-weights "dominance". They
   are not identical (Share = winner vs whole field; Closeness = winner vs #2),
   but worth a look — possible future merge into one dominance gate.
2. **`min()` is blind to how MANY gates are weak**, and the system is only as
   well-calibrated as its single worst threshold. One Medium gate and four
   Medium gates both report "Medium". A future "demote one level if ≥3 gates sit
   at the floor" rule would address this; deliberately not done now.

**Open items:** (1) thresholds are now realistic but still synthetic — re-tune
once the team's real generator defines the true volume/span distribution.
(2) Decide on the two design notes above. (3) distinct-days vs raw-records
Density numerator still open from the prior entry. Do NOT merge — Codex reviews
(re-derive the 5 users' expected confidences under the four gates), Nadim merges.

---

## 2026-06-20 — Claude: added Density (4th) gate (branch `branched-out-dih`)

**Context:** Nadim + co-founder flagged that the volume question must be
RELATIVE to the observation span, not an absolute count. "15 records" means
something very different over a week vs over three years. The existing N gate is
absolute and can't see this; Share/Closeness can both read High on a tiny,
unrepresentative sample. Real gap — agreed it's worth a gate.

**What changed (`detection.py`, additive — no existing outcome moved):**
- New **Gate Density** added to the weakest-link `min()`, alongside N/Share/
  Closeness. `confidence = min(all four)`.
- Metric = **distinct active days in the window / total days observed**
  (`_observed_days` = first→last record span of the FULL user frame, inclusive,
  min 1 so no div-by-zero). I used *distinct days*, NOT raw `records ÷ days` as
  originally phrased, on purpose: (a) raw record count is already the N gate's
  job — keying Density off it too makes the two gates collinear; (b) distinct
  days measures temporal spread and isn't inflatable by one chatty night.
  Switching the numerator back to raw record count is a one-line change if the
  team prefers the literal version.
- **N gate kept, not replaced.** The two compose into exactly the requested
  scaling: short span → N (absolute floor) binds → low count OK; long span →
  Density binds → needs many distinct active days = more records. N also stops a
  1-day dataset from scoring High on 100% coverage alone.
- `DetectionResult` gained a `density` field; `gates` dict gained `"density"`.
- Thresholds `DENSITY_HIGH=0.45`, `DENSITY_MEDIUM=0.20` — PLACEHOLDERS calibrated
  to the current ~28-day fixtures (User A covers ~0.52), same caveat as the N
  thresholds. Revisit on the fixture scale-up.
- `tests/test_detection.py` — 2 new tests: long-sparse-span → Density Low caps
  to Low; 15 nights over a 50-day span → Density Medium caps High→Medium.
  Frequent confidence left share-only (unchanged).

**Verified (NOT executed here — pandas DLL is blocked by Windows Application
Control on this machine, same root cause as the 06-18 venv note):**
- Standalone gate trace over all 4 fixture users using counts + RNG-replayed
  coverages: **all ground-truth contracts still hold** (harness should stay
  10/10). Density is never the binding gate on the current fixtures — it is
  *dormant* here by design; it only bites on long-sparse spans the fixtures
  don't yet contain.
- `py_compile` clean on all touched files.
- **Codex/Khaled must run `pytest tests/` + `python main.py ...` on a machine
  where pandas loads to confirm.**

**Open items:** (1) Density is untested by the HARNESS (only by unit tests) —
when fixtures scale up, add a 5th user with a long observation span + sparse
window so the harness exercises it. (2) Re-tune DENSITY_* alongside N_* at real
volumes. (3) Decide distinct-days vs raw-records numerator (I chose distinct
days; see above). Do NOT merge — Nadim merges after Codex agrees.

---

## 2026-06-20 — Claude: three-gate confidence model (branch `branched-out-dih`)

**Context:** review of `phase1_cdr/` found that the old share-only confidence
over-rated near-ties, and the harness silently skipped the area check whenever a
spec had `expected_area: null` + a confidence ceiling. User D's home detector
actually returned "Hamra" while ground truth claimed `null` — a misleading,
unenforced expectation (the original finding #1).

**What changed (all on `branched-out-dih`, NOT merged):**
- `detection.py` — replaced share-only confidence with a **three-gate,
  weakest-link** model. Three gates scored independently; confidence = the
  LOWEST:
    - **N** (sample size): High >=15, Medium >=5, else Low.
    - **Share** (winner / total): High >=40%, Medium >=10%, else Low.
    - **Closeness** (runner-up / winner, inverted): High <=0.30, Medium <=0.70,
      else Low = **near-tie**.
  Winner is still the area with the most calls. On a near-tie the result is
  tagged `Low: near tie` and lists `alternatives` (areas > 70% of the winner).
  `DetectionResult` gained `near_tie`, `alternatives`, `share`, `closeness`,
  `gates`, and a `confidence_label` property.
- **Frequent areas** is share-only (`detect_frequent_confidence`) — habits, not a
  single inferred location, so closeness/near-tie do not apply.
- `ground_truth.json` / `dev_fixtures.py` — D's misleading `null` areas replaced
  with the real plurality areas (independently tallied), plus
  `expected_alternatives` for B-home and D. Still computed WITHOUT importing
  `detection.py`.
- `validate.py` / `main.py` — check `alternatives` + frequent confidence; table
  now shows the confidence label and alternatives.
- `tests/test_detection.py` — rewritten for the three gates (N-cap, near-tie +
  alternatives, share-cap, frequent share-only). **9 pass; harness 10/10.**

**IMPORTANT open item — N gate thresholds are PLACEHOLDERS.** `N_HIGH=15` /
`N_MEDIUM=5` are scaled to the current tiny fixtures (~20 calls/window) so User A
can reach High. They are NOT realistic. **Next:** scale `dev_fixtures.py` up to
realistic volumes (~10x, e.g. A ~200 overnight calls, same ratios) and raise
`N_HIGH` toward ~50. Design decision log for the gates is in this entry.

**Next for Codex:** independently re-derive the four users' expected confidences
under the three-gate rules and confirm `ground_truth.json` matches; scrutinize
the gate thresholds; do NOT merge — human (Nadim) merges after both agents agree.

---

## 2026-06-19 — Claude: collaboration scaffolding set up
- Added `COLLAB.md` (protocol) and this `HANDOFF.md`.
- No code in `phase1_cdr/` touched. Baseline is commit `0021c27` on `main`.
- **Next:** Codex to review `phase1_cdr/` (run tests + `validate.py`, scrutinize
  `detection.py`, and independently sanity-check `ground_truth.json` — do NOT just
  trust it, since it may have been reverse-engineered from the code). Report
  findings here grouped as Bugs / Test gaps / Correctness concerns / Nits, with
  file:line. Do not fix — leave fixes for Claude.
