# Handoff Log

Shared scratchpad between Claude Code and Codex. Newest entries on top.
Each entry: who, what changed (with file:line where useful), what's left, and any
disagreement or open question. See `COLLAB.md` for the protocol.

## 2026-06-22 — Claude: merged Dependabot CI bump (PR #4) + pruned merged branches

Housekeeping session, authorized by Nadim. No algorithm/code-under-test changes.

- **PR #4 merged** (`de0a05d`): grouped github-actions bump in `.github/workflows/ci.yml`
  — `actions/checkout` v4→v7, `actions/setup-python` v5→v6. Both CI `test` checks
  green on the new versions before merge. The 2-dot diff *appeared* to also revert
  this HANDOFF's session-close entry, but that was a stale-branch artifact: the
  branch's merge-base was `e1746a2` and it touched only `ci.yml`, so the 3-way merge
  left HANDOFF.md untouched (verified post-merge).
- **Stale branches pruned** (all fully merged into `main`, zero unmerged commits):
  remote `branched-out-dih`, remote `claude/ci-github-actions`, local
  `codex/review-branched-out-dih`, and the auto-deleted Dependabot branch.

**State:** `main` is the only branch (plus this one), green, Phase 1 still shipped at
`v1.0-phase1`. Standing future work unchanged: Issues #1 (re-tune `N_*`/`DENSITY_*`)
and #2 (`min()` design notes).

---

## 2026-06-21 — Claude: session close — Phase 1 shipped & tagged; branch protection skipped

Final state at end of session. Everything below is on `main` and green.

- **PR #3 merged** (`claude/repo-hardening` → `main`, commit `e1746a2`): root
  `README.md`, `.github/dependabot.yml`, `.github/PULL_REQUEST_TEMPLATE.md`. First
  clean run through the PR flow.
- **`v1.0-phase1`** annotated tag pushed, and a **GitHub Release** published from it
  (release notes on the repo sidebar).
- **Dependabot** security alerts + auto-fixes enabled; Issues **#1** (threshold
  re-tune) and **#2** (`min()` design notes) are the canonical tracker for the
  standing items now.
- **Branch protection: SKIPPED.** Rulesets/classic protection are plan-gated on a
  free private repo (403 "Upgrade to GitHub Pro or make this repository public").
  Per Nadim, we rely on the honor-system PR flow in `COLLAB.md` instead. If the repo
  later goes public or Pro, add a ruleset on `main` requiring the `test` check + a PR
  with an admin bypass — that's the only missing piece. (Saved as a project memory so
  it isn't re-attempted.)

**Phase 1 is complete.** Next work (when picked up) is Issues #1/#2 or Phase 2.

---

## 2026-06-21 — Claude: repo hardening — root README, Dependabot, PR template, Issues, branch protection (branch `claude/repo-hardening`)

Portfolio + process hardening, approved by Nadim. Several pieces are GitHub-state
(not file commits); the file changes are on this branch as a PR — the **first run
through the new PR-based merge flow** below.

**Files on this branch:**
- **Root `README.md` (new)** — the repo had no top-level README, so the GitHub
  landing page showed a bare file list and the CI badge (in `phase1_cdr/README.md`)
  wasn't visible there. New root README frames the multi-phase vision, the
  four-gate model, and the two-agent collaboration workflow, and carries the badge.
- **`.github/dependabot.yml` (new)** — pip ecosystem on `/phase1_cdr`, github-actions
  on `/`, both **monthly + grouped** to avoid PR noise on a 3-dep project. The
  github-actions entry also auto-clears the "Node 20 deprecated" CI warning when
  newer action majors ship.
- **`.github/PULL_REQUEST_TEMPLATE.md` (new)** — reinforces the protocol at merge
  time (CI green / other agent reviewed / HANDOFF updated / no status in COLLAB).

**GitHub-state changes (already applied, not in the diff):**
- **Dependabot security alerts + automated security fixes** enabled on the repo.
- **Issues opened for the standing items** (migrated out of this log so they're
  visible + closeable): **#1** re-tune `N_*`/`DENSITY_*` on the real generator;
  **#2** the two `min()` confidence-design notes. These are the canonical tracker
  now — this log just points at them.
- **Annotated tag `v1.0-phase1`** marking Phase 1 complete — applied **after this
  PR merges** so the milestone captures the documented state.
- **Branch protection on `main`** — intended: require the CI status check + a PR
  before merge, with an admin bypass for Nadim. **[CORRECTION 2026-06-21: NOT
  applied — plan-gated (free private repo → 403, needs Pro or public). Nadim chose
  to SKIP enforcement. See the session-close entry above.]**

**Workflow note:** with branch protection live, the normal path is now PR →
CI green → Nadim merges. Agents still never merge.

**Next:** Codex reviews this PR; Nadim merges it; then I apply the
`v1.0-phase1` tag.

---

## 2026-06-21 — Claude: added GitHub Actions CI (branch `claude/ci-github-actions`)

Closes the standing open item from the merge: the test suite no longer depends
on one machine being able to load pandas.

**What changed:** new `.github/workflows/ci.yml`. Triggers on **every push and
every pull request** (no branch filter — covers `main`, the feature branches,
and review PRs). On `ubuntu-latest` with **Python 3.12** (matches Khaled's
verified 3.12.10), it:
1. installs `phase1_cdr/requirements.txt` (pip cached on that file's hash),
2. runs `pytest tests/`,
3. runs the validation harness `python main.py sample_data.csv ground_truth.json`.

Setup was read off the existing structure, not assumed: all steps use
`working-directory: phase1_cdr` because that's where `requirements.txt`, `tests/`,
and `conftest.py` live (conftest puts that dir on `sys.path` so tests import
`detection`/`loader` directly). Harness step included on purpose — `main.py`
exits non-zero on any failure, so CI enforces the real 12/12 integration check,
not just the 13 unit tests.

**Verification:** ubuntu's Python loads pandas fine, so the push that creates
this branch is itself the first live CI run — watch the Actions tab. I could not
run `pytest` locally (pandas still blocked by Windows Application Control on this
machine), which is exactly the dependency this CI removes.

**Next:** per protocol, not merged. Codex reviews the workflow, then Nadim merges
`claude/ci-github-actions` to `main`. Once green, add a status badge to the
README if Nadim wants one.

---

## 2026-06-21 — Claude: doc-drift fix applied (option 2) + `branched-out-dih` MERGED to `main` (Nadim's call)

Two things, both authorized explicitly by Nadim this session.

**1. Doc-drift fix — option 2.** Nadim chose the self-enforcing convention from
the open question below. Implemented in `COLLAB.md`:
- Added **rule 3** under "Two rules that prevent disaster": *"`COLLAB.md` is
  rules-only. Any branch or merge status goes in `HANDOFF.md`, never here. If you
  find status text in `COLLAB.md`, move it."*
- Replaced the `Current active branch` subsection (which carried a mutable commit
  list + Status line) with a stable pointer to `HANDOFF.md`'s top entry.
The mutable status now lives in exactly one place, so the protocol doc can't go
stale and contradict the running log again. The open question below is now
**resolved** — kept for the record.

**2. Merge to `main`.** With the verification green (13 passed / 12/12) and both
agents agreed, **Nadim gave explicit permission to merge**. Merged
`branched-out-dih` → `main` and pushed. `main` now carries the full four-gate
confidence model. The feature branch has served its purpose.

**Next:** Phase 1's confidence work is done and on `main`. Standing open items
for whoever picks up next (none are blockers): re-tune `N_*` / `DENSITY_*` once
the team's real synthetic generator fixes the true volume/span distribution; the
two `min()`-design notes (Share/Closeness overlap; `min()` blind to how many
gates are weak), both deferred to real-data calibration; and consider a GitHub
Actions CI (`pytest` on push) so the suite no longer depends on one machine being
able to load pandas.

---

## 2026-06-21 — Claude: QUESTION for Nadim — should branch status live ONLY in `HANDOFF.md`? [RESOLVED — option 2, see entry above]

**Not a change request — asking before doing anything structural.** I only
updated the Status line in `COLLAB.md`'s `Current active branch` subsection to
reflect today's green run. I did NOT restructure that file. The question below is
open for your call.

**The issue.** Our two docs have distinct jobs: `COLLAB.md` = stable *protocol*
(the rules you paste to an agent at session start); `HANDOFF.md` = the *running
intent log* (mutable, newest-on-top state). But `COLLAB.md`'s `Current active
branch` subsection carries mutable state — a numbered list of the commits on the
branch plus a **Status** line. That's a snapshot, not a rule, so it lives in the
file that's *supposed* to be stable.

**Why it just bit us.** Before I touched it, `HANDOFF.md` correctly said the
branch was verified merge-ready after the green run, but `COLLAB.md` still said
"merge-ready pending one verification run." The two docs contradicted each other —
and the *protocol* doc (the one we paste FIRST when onboarding an agent) was the
stale one, understating progress. Per our own core principle (each agent's view
is a frozen snapshot; git is the only shared memory), a fresh Claude/Codex
session reading `COLLAB.md` first could conclude the run still needs doing and
redo it — not realizing it's already green. Root cause is structural: **mutable
state living in the file meant for stable rules.** Updating the status line (as I
just did) fixes it for now but the drift will recur next time work advances.

**The question — do we want a durable fix?** Options, lightest → heaviest:
1. **Do nothing structural** — keep updating the `COLLAB.md` status line by hand
   each session. Simplest; the drift just keeps coming back.
2. **Add a rule to `COLLAB.md`** under "Two rules that prevent disaster":
   *"`COLLAB.md` is rules-only. Any branch/merge status goes in `HANDOFF.md`. If
   you find status text in `COLLAB.md`, move it."* Then trim the `Current active
   branch` subsection down to a stable pointer at `HANDOFF.md`. Self-enforcing
   for any agent that reads the protocol.
3. **Single source of truth** — pin one `## STATUS` block at the very top of
   `HANDOFF.md` that every handoff updates in place, so no one scans entries to
   learn the current state.
My lean is **#2**, but this is your call, Nadim — say the word and I'll implement
whichever you pick. Nothing structural changed yet.

---

## 2026-06-21 — Khaled/Claude: verification run GREEN — branch confirmed merge-ready

Ran the only remaining gate on `branched-out-dih` at HEAD `a636071`, in
`phase1_cdr/.venv` (Python 3.12.10, pandas 3.0.3 — loads fine):
- `pytest tests/` → **13 passed** (matches the expected 13).
- `python main.py sample_data.csv ground_truth.json` → **12/12 passed (100%)**
  (matches the expected 12; E-work row included).

Per-user results line up with Codex's independent gate trace: A home/work High;
B home `Low: near tie` (alt Hamra) / work Medium; C home/work `Insufficient
data`; D home `Low: near tie` (alt Achrafieh) / work `Low: near tie` (alts
Mazraa/Verdun); E home `Low` (Density-bound) / work `Insufficient data`.

**State:** the static trace is now confirmed by execution at HEAD. Nothing
changed in code — this entry only records the green run. Branch is **agreed by
both agents and verified**; the next action is **Nadim merges `branched-out-dih`
to `main`**. I did NOT merge (per protocol, only Nadim merges).

---

## 2026-06-20 — Claude: folded Codex's review into `branched-out-dih` (merge-ready)

Reviewed Codex's commit `f7d7d9b` (originally on local branch
`codex/review-branched-out-dih`) and traced it against the fixtures. **Agreed
with all of it** — the `validate.py` null-area fix is the correct root-cause fix
for the bug flagged in the first review; C/E tightening to exact `Insufficient
data` is correct (C is evening-only, E has no weekday-daytime records, so both
windows are genuinely empty); the near-tie unit-test rescale (6/5 → 30/25)
correctly re-isolates the closeness gate after `N_MEDIUM` rose to 15.

Codex could not push (its sandbox approval policy blocks outbound network to the
GitHub remote), so the commit was local-only. Since it's a clean +1 fast-forward
and is reviewed/approved, per Nadim's call I **fast-forwarded `branched-out-dih`
to `f7d7d9b` and pushed** — no separate review branch is kept. `origin/branched-
out-dih` now ends at `f7d7d9b`; Khaled can pull it.

**State:** branch is the agreed state of both agents, **merge-ready pending one
re-run.** Ground truth + harness logic + tests all changed since Khaled's last
green run, so his 11/11 no longer covers HEAD.

**Next (the only remaining gate):** Khaled pulls `branched-out-dih`, runs
`pytest tests/` (expect **13 passed**) and `python main.py sample_data.csv
ground_truth.json` (expect **12/12** — E-work added one row). If green, Nadim
merges to `main`. Static trace says it passes; execution must confirm.

---

## 2026-06-20 — Codex: static review of `branched-out-dih` (branch `codex/review-branched-out-dih`)

Reviewed the five Claude commits in scope after `git fetch --all`:
`36d0ac6`, `fda4a26`, `9b4dc0b`, `2a2b600`, `78323b3`. Per Nadim's instruction,
I did NOT run pytest or `main.py`; I read the recorded execution from git instead
(`2a2b600` says `pytest tests/` 11 passed and `main.py` harness 11/11). The
Claude branch's `ground_truth.json` contained 11 checks, so Khaled's 11/11 is
consistent with the committed spec count. My Codex branch adds one missing work
expectation for User E, so the next harness run on this branch should have 12
rows.

**Bugs**
- `phase1_cdr/validate.py:40` claimed an area check independent of confidence,
  but the old `expected_area: null` path skipped the area assertion whenever a
  confidence ceiling was present. That meant C's no-window specs could pass even
  if a detector returned a bogus `Low` area. Fixed on this branch at
  `phase1_cdr/validate.py:45` and covered by `phase1_cdr/tests/test_validate.py:9`.
- `phase1_cdr/ground_truth.json:68` had no User E work check, despite the review
  target being A-E home/work. Added exact `Insufficient data` for E work in
  `phase1_cdr/dev_fixtures.py:257` and `phase1_cdr/ground_truth.json:74`.

**Test gaps**
- C home/work were ceilings (`<= Low`) rather than exact no-window expectations.
  Tightened them to exact `Insufficient data` in `phase1_cdr/dev_fixtures.py:236`
  and `phase1_cdr/ground_truth.json:43`.
- The near-tie unit test was previously also capped by the N gate, so it did not
  isolate the closeness gate. Rescaled it to 30 vs 25 records and added explicit
  gate assertions at `phase1_cdr/tests/test_detection.py:73`.
- Exact `Low` confidence alone cannot prove which gate bound User E. I fixed the
  overclaiming docs/comments in `phase1_cdr/dev_fixtures.py:155` and
  `phase1_cdr/README.md:108`; the current proof is the independent gate trace
  below plus density-gate unit assertions at `phase1_cdr/tests/test_detection.py:166`
  and `phase1_cdr/tests/test_detection.py:181`. If we want the harness itself to
  prove sole binding, add expected gate labels to `ground_truth.json`.

**Correctness concerns**
- Independent gate derivation from the fixture counts (`phase1_cdr/dev_fixtures.py:111`,
  `:123`, `:135`, `:142`, `:159`) and committed fixture dates:
  - A home: 560/50/30 = 640 total, observed span 364d, 312 active home days.
    Gates = N High, Share 0.875 High, Closeness 0.089 High, Density 0.857 High
    -> `High`. A work: 360/40/20 = 420 total, 207 active work days; gates all
    High -> `High`. User A clears High with a wide margin.
  - B home: 210/180/110 = 500 total, density 169/181 = 0.934. Gates = N High,
    Share 0.420 High, Closeness 0.857 Low, Density High -> actual `Low`, which
    satisfies the `<= Medium` ground-truth ceiling and lists Hamra as the alt.
    B work: 220/140/130 = 490 total; N High, Share 0.449 High, Closeness 0.636
    Medium, Density 0.696 High -> `Medium`.
  - C home/work: no records in either window -> `Insufficient data`.
  - D home: 260/230 = 490 total; N High, Share 0.531 High, Closeness 0.885 Low,
    Density 0.934 High -> actual `Low`, satisfying `<= Medium` and alt
    Achrafieh. D work: 160/140/130/90 = 520 total; N High, Share 0.308 Medium,
    Closeness 0.875 Low, Density 0.702 High -> `Low`, matching `<= Low` with
    alts Mazraa/Verdun.
  - E home: 30/0 = 30 total, 27 active home days over 365 observed days. Gates =
    N Medium, Share 1.000 High, Closeness 0.000 High, Density 0.074 Low -> exact
    `Low`, and Density is the only Low gate. E work: no work-window records ->
    `Insufficient data`.
- Density implementation looks correct for the requested metric. Empty windows
  return before division (`phase1_cdr/detection.py:172`), single-day spans are
  `max-min + 1` days (`phase1_cdr/detection.py:151`, `:162`), the denominator is
  passed from the full user frame by `detect_home`/`detect_work`, and active days
  are distinct normalized dates (`phase1_cdr/detection.py:189`). The weakest-link
  `min()` includes Density at `phase1_cdr/detection.py:196`.
- Alternatives are internally consistent with the closeness gate: `Low` closeness
  starts at runner-up/winner `> 0.70`, and alternatives use the same strict
  cutoff at `phase1_cdr/detection.py:203`. Exact 0.70 is Medium and not an
  alternative, which is coherent.
- I agree with distinct active days as the Density numerator. Raw records/day
  would duplicate the N gate and can be inflated by one unusually chatty night;
  distinct days measures temporal spread, which is the missing signal. Keep N
  and Density: N is the absolute sample floor; Density is coverage relative to
  observation span.
- The retuned thresholds are defensible for these synthetic 500-5000-call/user
  fixtures (`N_HIGH=50`, `N_MEDIUM=15`, `DENSITY_HIGH=0.40`,
  `DENSITY_MEDIUM=0.15` at `phase1_cdr/detection.py:46` and
  `phase1_cdr/detection.py:69`). They should still be recalibrated on the real
  generator's volume/span distribution. Share and Closeness are scale-free, so
  leaving them untouched is reasonable.
- I agree the two gate-design notes are later real-data items, not blockers for
  this merge: Share and Closeness do overlap, and `min()` ignores how many gates
  are weak. Both are calibration/model-design questions that need real
  distributions; the current branch is internally coherent and safer than the
  previous share-only model.

**Nits**
- `phase1_cdr/README.md:26` still said `dev_fixtures.py` generated four users;
  fixed to five.
- `phase1_cdr/README.md:102` showed no E work expectation; fixed to `none,
  Insufficient data`.

No merge performed. Changes are isolated on `codex/review-branched-out-dih`.

---

> **2026-06-20 — Codex: branch `branched-out-dih` is pushed and ready for your
> review.** The thresholds are now re-tuned for realistic 500–5000-call/user data
> and the suite actually runs here (pandas loads in `.venv` again): `pytest
> tests/` 11 passed, `main.py` harness 11/11. Please re-derive the 5 users'
> expected confidences under the four gates independently, scrutinise the new
> `N_*` / `DENSITY_*` values, and weigh the two gate-design notes in the entry
> below. Do NOT merge — Nadim merges once we agree.

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
