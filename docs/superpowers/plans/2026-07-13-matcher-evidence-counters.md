# Matcher Evidence Counters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add descriptive evidence tallies (direct records, mutual calls, mutual locations) to the contact matcher — shown as a strip in the matcher card and exported to a new "Evidence counts" sheet.

**Architecture:** Counts are computed in the pure gate engine (`gates.build_evidence_counts`, I/O-free) from the same facts the findings use, composed into the match payload by `service.compute_match`, stored on save, and copied verbatim into the workbook. One new SQL query (`repo.area_tallies`) supplies per-area record volume, which the engine currently cannot see.

**Tech Stack:** Python 3.11 / Flask / SQLCipher / openpyxl; vanilla no-build ES modules + Node's built-in test runner.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-13-matcher-evidence-counters-design.md`. Read it first.
- **Counts are NOT verdicts:** no confidence, no strength pills, no gates. They can never change an existing finding's rating.
- **Phase 1 is FROZEN:** `git diff --stat main -- phase1_cdr/` must stay empty.
- **Layering (ADR 0001):** `repo.py` = SQL only (takes a `conn`, returns dicts, never commits); `gates.py` = pure, no I/O, no Flask; `service.py` = orchestration; routes own the unit-of-work. Export reads STORED JSON and never recomputes.
- **Backward compatibility:** payloads saved before this change have no `evidence_counts` — UI and export must render "—" and never crash.
- **Distinctive/common classification is dataset-mode aware** and MUST reuse the same helper the mutual finding uses, so the counter and the finding can never disagree.
- Verify with: `.venv\Scripts\python.exe -m pytest tests\phase2a tests\architecture phase1_cdr\tests -q` (254 passing before this work), `.venv\Scripts\python.exe -m ruff check app tests main.py tools`, `node --check` on changed JS, `node --test app\web\js\components.test.mjs`.

---

### Task 1: Pure count engine in `gates.py`

**Files:**
- Modify: `app/matching/gates.py` (add `classify_shared_contacts` helper + `build_evidence_counts`; refactor `_mutual_finding` to use the helper)
- Test: `tests/phase2a/test_matching.py` (append to the "adaptive gates" section)

**Interfaces:**
- Consumes: the existing `facts` dict (`contacts_a`, `contacts_b`, `contact_commonality`, `other_users`, `direct`, `co_events`, plus two NEW keys from Task 2: `area_tallies_a`, `area_tallies_b` — `{area: record_count}`).
- Produces:
  - `classify_shared_contacts(shared, commonality, other_users, mode, spread_median) -> list[str]` (the distinctive subset; `_mutual_finding` and `build_evidence_counts` both call it).
  - `build_evidence_counts(facts, mode, spread_median) -> dict` with the exact shape in the spec (`direct`, `mutual_calls.{distinctive,common}`, `mutual_locations.{meet_up,non_meet_up}`).
  - `build_findings` gains `"evidence_counts": build_evidence_counts(...)` in its return dict (and in the zero-record early-return path, where every count is 0).

- [ ] **Step 1: Write the failing tests**

```python
def test_evidence_counts_direct_and_mutual_call_split():
    facts = _facts(
        contacts_a={"P1": 5, "P2": 4, "P9": 3},
        contacts_b={"P1": 6, "P2": 2, "P9": 1},
        contact_commonality={"P1": 0, "P2": 0, "P9": 9},  # P9 common (20% of 10)
    )
    c = gates.build_findings(facts)["evidence_counts"]
    assert c["direct"] == {"records": 12, "calls": 10, "sms": 2, "a_to_b": 6, "b_to_a": 6}
    assert c["mutual_calls"]["distinctive"] == {
        "contacts": 2, "records_a": 9, "records_b": 8, "records": 17}   # P1+P2
    assert c["mutual_calls"]["common"] == {
        "contacts": 1, "records_a": 3, "records_b": 1, "records": 4}    # P9


def test_evidence_counts_location_buckets_are_disjoint_by_area():
    """An area where they MET is never also counted as shared-only: the buckets
    partition the shared areas, so their totals sum without double counting."""
    facts = _facts(
        areas_a={"X", "Q", "SoloA"}, areas_b={"X", "Q", "SoloB"},
        area_tallies_a={"X": 10, "Q": 7, "SoloA": 3},
        area_tallies_b={"X": 8, "Q": 5, "SoloB": 2},
        # co_events (from _facts) are all in area X -> X is the meet-up bucket
    )
    loc = gates.build_findings(facts)["evidence_counts"]["mutual_locations"]
    assert loc["meet_up"] == {"areas": 1, "records_a": 10, "records_b": 8, "records": 18}
    assert loc["non_meet_up"] == {"areas": 1, "records_a": 7, "records_b": 5, "records": 12}
    # SoloA/SoloB are not shared -> counted nowhere
    assert loc["meet_up"]["areas"] + loc["non_meet_up"]["areas"] == 2


def test_evidence_counts_use_the_same_classification_as_the_finding():
    """Close-knit mode: the counter's distinctive/common split must match the
    mutual finding's, in both modes -- one classifier, two consumers."""
    facts = _ck_facts(contact_commonality={"P1": 1, "P2": 8, "P3": 7})
    result = gates.build_findings(facts)
    counts = result["evidence_counts"]["mutual_calls"]
    shared = _by_type(result)["mutual_contacts"]["evidence"]["shared_contacts"]
    distinctive_in_finding = sum(1 for c in shared if c["distinctive"])
    assert counts["distinctive"]["contacts"] == distinctive_in_finding == 1
    assert counts["common"]["contacts"] == 2


def test_evidence_counts_zero_when_nothing_shared():
    facts = _facts(
        contacts_a={"PA": 1}, contacts_b={"PB": 1}, contact_commonality={},
        direct={"total": 0, "calls": 0, "sms": 0, "a_to_b": 0, "b_to_a": 0,
                "first": None, "last": None},
        co_events=[], areas_a={"A1"}, areas_b={"B1"},
        area_tallies_a={"A1": 4}, area_tallies_b={"B1": 5})
    c = gates.build_findings(facts)["evidence_counts"]
    assert c["direct"]["records"] == 0
    assert c["mutual_calls"]["distinctive"]["contacts"] == 0
    assert c["mutual_locations"]["meet_up"]["areas"] == 0
    assert c["mutual_locations"]["non_meet_up"]["areas"] == 0


def test_evidence_counts_present_even_when_a_target_has_no_records():
    c = gates.build_findings(_facts(n_b=0, span_b=None))["evidence_counts"]
    assert c["direct"]["records"] == 0 and c["mutual_calls"]["common"]["records"] == 0
```

Also extend the `_facts()` helper's baseline dict with the two new keys so every existing test keeps working:

```python
        "area_tallies_a": {"X": 10, "Y": 4},
        "area_tallies_b": {"X": 8, "Z": 6},
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests\phase2a\test_matching.py -q -k evidence_counts`
Expected: FAIL — `KeyError: 'evidence_counts'`

- [ ] **Step 3: Implement**

In `gates.py`, extract the classifier the mutual finding already performs inline, so both callers share it:

```python
def classify_shared_contacts(shared, commonality, other_users, mode, spread_median):
    """The distinctive subset of `shared`. Dataset-mode aware: in strangers mode a
    contact is common when the 20%-of-others discount (with the COMMON_MIN_USERS
    floor) says so; in close-knit mode when it is no rarer than the dataset's
    median shared-contact spread. ONE classifier, two consumers -- the mutual
    finding and the evidence counter must never label a contact differently."""
    if mode == CLOSE_KNIT:
        return [p for p in shared if commonality.get(p, 0) + 2 < spread_median]
    return [p for p in shared if not _is_common(commonality.get(p, 0), other_users)]
```

Rewrite the head of `_mutual_finding` to call it (replacing the inline `if mode == CLOSE_KNIT: distinctive = [...] else: distinctive = [...]` branch), keeping the strangers-mode `MUTUAL_MIN_DISTINCTIVE` suppression and the close-knit rating branch exactly as they are today.

```python
def _bucket(items, tallies_a, tallies_b, key) -> dict:
    """One count bucket: how many items, and each side's record volume in them."""
    records_a = sum(tallies_a.get(i, 0) for i in items)
    records_b = sum(tallies_b.get(i, 0) for i in items)
    return {key: len(items), "records_a": records_a, "records_b": records_b,
            "records": records_a + records_b}


def build_evidence_counts(facts: dict, mode: str, spread_median: int) -> dict:
    """Descriptive tallies of the raw evidence -- NO gates, NO confidence (a count
    is not a verdict; same rule as the frequency explorer). Derived from the same
    facts the findings use, so the two can never disagree."""
    contacts_a = facts["contacts_a"]
    contacts_b = facts["contacts_b"]
    shared = sorted(set(contacts_a) & set(contacts_b))
    distinctive = classify_shared_contacts(
        shared, facts["contact_commonality"], facts["other_users"], mode, spread_median)
    common = [p for p in shared if p not in set(distinctive)]

    shared_areas = facts["areas_a"] & facts["areas_b"]
    meet_up = sorted({e["area"] for e in facts["co_events"]} & shared_areas)
    # Disjoint by area: an area they met in is never ALSO counted as shared-only.
    non_meet_up = sorted(shared_areas - set(meet_up))
    areas_a = facts.get("area_tallies_a", {})
    areas_b = facts.get("area_tallies_b", {})

    d = facts["direct"]
    return {
        "direct": {"records": d["total"], "calls": d["calls"], "sms": d["sms"],
                   "a_to_b": d["a_to_b"], "b_to_a": d["b_to_a"]},
        "mutual_calls": {
            "distinctive": _bucket(distinctive, contacts_a, contacts_b, "contacts"),
            "common": _bucket(common, contacts_a, contacts_b, "contacts"),
        },
        "mutual_locations": {
            "meet_up": _bucket(meet_up, areas_a, areas_b, "areas"),
            "non_meet_up": _bucket(non_meet_up, areas_a, areas_b, "areas"),
        },
    }
```

In `build_findings`, add `"evidence_counts": build_evidence_counts(facts, dataset_context["mode"], spread_median)` to BOTH return dicts (the zero-record early return and the normal one). In the early-return path the direct/shared facts are already all-zero/empty, so the same call yields zeroed counts — no special casing.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests\phase2a\test_matching.py -q`
Expected: PASS (all prior matcher tests still green — the classifier refactor must not change any rating)

- [ ] **Step 5: Commit**

```bash
git add app/matching/gates.py tests/phase2a/test_matching.py
git commit -m "claude: evidence counters - pure count engine + shared classifier"
```

---

### Task 2: Per-area tallies in `repo.py` + payload composition in `service.py`

**Files:**
- Modify: `app/matching/repo.py` (add `area_tallies`)
- Modify: `app/matching/service.py` (pass the two new facts; `build_findings` already returns the counts)
- Test: `tests/phase2a/test_matching.py`

**Interfaces:**
- Consumes: `gates.build_evidence_counts` (Task 1) via `gates.build_findings`.
- Produces: `repo.area_tallies(conn, dataset_id, phone_number) -> dict[str, int]` (`{area: record_count}`); the `/api/match` payload gains a top-level `evidence_counts` key.

- [ ] **Step 1: Write the failing test**

The fixture pair (A=100, B=200) from the existing `ROWS`: A's shared areas with B are `Cafe`/`Edge`/`Downtown` (meet-ups) and `Far` (shared, no time overlap). Hand-worked from `ROWS`: A has 1 record in Cafe... — count them from the fixture rather than trusting memory:

```python
def test_match_payload_carries_evidence_counts(client, pair):
    a, b = pair
    data = _match(client, a, b).get_json()["data"]
    c = data["evidence_counts"]
    # direct: the 4 A<->B records (2 calls, 2 SMS, 2 each way)
    assert c["direct"] == {"records": 4, "calls": 2, "sms": 2, "a_to_b": 2, "b_to_a": 2}
    # shared contacts P1,P2,P9 -- all distinctive here (P9's 2 other users sit
    # under the COMMON_MIN_USERS floor), 1 record each side per contact
    assert c["mutual_calls"]["distinctive"] == {
        "contacts": 3, "records_a": 3, "records_b": 3, "records": 6}
    assert c["mutual_calls"]["common"]["contacts"] == 0
    # locations: Cafe/Edge/Downtown are meet-up areas; Far is shared-only
    loc = c["mutual_locations"]
    assert loc["meet_up"]["areas"] == 3
    assert loc["non_meet_up"] == {"areas": 1, "records_a": 1, "records_b": 1, "records": 2}
    # A has 3 Cafe records (2 pairings + 1 extra) + 1 Edge + 1 Downtown = 5
    assert loc["meet_up"]["records_a"] == 5
    assert loc["meet_up"]["records_b"] == 3      # 1 each in Cafe, Edge, Downtown


def test_evidence_counts_are_symmetric(client, dataset_id, pair):
    a, b = pair
    ab = _match(client, a, b).get_json()["data"]["evidence_counts"]
    ba = _match(client, b, a).get_json()["data"]["evidence_counts"]
    assert ab == ba
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests\phase2a\test_matching.py -q -k "payload_carries_evidence or counts_are_symmetric"`
Expected: FAIL — `KeyError: 'area_tallies_a'` (or a zeroed location bucket)

- [ ] **Step 3: Implement**

In `repo.py`, next to `area_set`:

```python
def area_tallies(conn, dataset_id, phone_number) -> dict[str, int]:
    """area -> how many records the subscriber has there. `area_set` gives only
    the set; the evidence counter needs the per-area volume."""
    rows = conn.execute(
        "SELECT area, COUNT(*) AS n FROM cdr_records "
        "WHERE dataset_id = ? AND phone_number = ? GROUP BY area",
        (dataset_id, phone_number),
    ).fetchall()
    return {r["area"]: r["n"] for r in rows}
```

In `service.py`, replace the two `areas_a` / `areas_b` lines so the tallies are fetched once and the sets derived from them (one query per side instead of two):

```python
    area_tallies_a = repo.area_tallies(conn, dataset_id, phone_a)
    area_tallies_b = repo.area_tallies(conn, dataset_id, phone_b)
    areas_a, areas_b = set(area_tallies_a), set(area_tallies_b)
```

and add to the `facts` dict:

```python
        "area_tallies_a": area_tallies_a, "area_tallies_b": area_tallies_b,
```

Leave `repo.area_set` in place (other callers/tests may use it).

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests\phase2a -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/matching/repo.py app/matching/service.py tests/phase2a/test_matching.py
git commit -m "claude: evidence counters - per-area tallies + payload composition"
```

---

### Task 3: Evidence strip + detail table in the matcher card

**Files:**
- Modify: `app/web/js/components.js` (add `evidenceCountsBlock`, render it in `matchFindingsBlock`)
- Modify: `app/web/css/app.css` (`.evidence-strip` styles)
- Test: `app/web/js/components.test.mjs`

**Interfaces:**
- Consumes: `payload.evidence_counts` (Task 2).
- Produces: `evidenceCountsBlock(counts) -> HTMLElement|null` (null when `counts` is absent — old saved payloads).

- [ ] **Step 1: Write the failing tests**

```javascript
const COUNTS = {
  direct: { records: 12, calls: 8, sms: 4, a_to_b: 6, b_to_a: 6 },
  mutual_calls: {
    distinctive: { contacts: 5, records_a: 20, records_b: 27, records: 47 },
    common: { contacts: 2, records_a: 4, records_b: 6, records: 10 },
  },
  mutual_locations: {
    meet_up: { areas: 3, records_a: 18, records_b: 15, records: 33 },
    non_meet_up: { areas: 4, records_a: 22, records_b: 19, records: 41 },
  },
};

test("matchFindingsBlock: evidence strip summarizes the raw counts", () => {
  const block = matchFindingsBlock({
    pair: PAIR, findings: [FINDING()], caveats: [], no_link: false, details: {},
    evidence_counts: COUNTS,
  });
  assert.match(block.textContent, /Direct 12/);
  assert.match(block.textContent, /Mutual calls 57 across 7 contacts/);  // totals
  assert.match(block.textContent, /3 meet-up/);
  assert.match(block.textContent, /4 shared-only/);
});

test("matchFindingsBlock: evidence strip carries NO strength pill", () => {
  const block = matchFindingsBlock({
    pair: PAIR, findings: [], caveats: [], no_link: true, details: {},
    evidence_counts: COUNTS,
  });
  // a count is not a verdict: the no-link payload must show counts but no pill
  assert.match(block.textContent, /Direct 12/);
  assert.doesNotMatch(block.textContent, /pill-high|pill-low/);
});

test("matchFindingsBlock: payload without evidence_counts renders no strip", () => {
  const block = matchFindingsBlock({
    pair: PAIR, findings: [FINDING()], caveats: [], no_link: false, details: {},
  });
  assert.doesNotMatch(block.textContent, /Direct 12/);
  assert.doesNotMatch(block.textContent, /Evidence/);
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `node --test app\web\js\components.test.mjs`
Expected: FAIL — strip text absent

- [ ] **Step 3: Implement**

In `components.js`, above `matchFindingsBlock`:

```javascript
// Raw evidence tallies (spec 2026-07-13-matcher-evidence-counters-design.md).
// Deliberately pill-free: a count is NOT a gated verdict (same rule as the
// frequency explorer's tallies). The strip summarizes; the table breaks the
// counts into their buckets. Returns null for payloads saved before this
// existed, so old saved matches render exactly as they used to.
export function evidenceCountsBlock(counts) {
  if (!counts) return null;
  const mc = counts.mutual_calls || {};
  const ml = counts.mutual_locations || {};
  const d = counts.direct || {};
  const callRecords = (mc.distinctive?.records || 0) + (mc.common?.records || 0);
  const callContacts = (mc.distinctive?.contacts || 0) + (mc.common?.contacts || 0);
  const summary =
    `Direct ${d.records || 0} · ` +
    `Mutual calls ${callRecords} across ${callContacts} contacts · ` +
    `Locations ${ml.meet_up?.areas || 0} meet-up / ${ml.non_meet_up?.areas || 0} shared-only`;

  const row = (label, b, itemKey, itemLabel) => [
    el("span", { class: "k" }, label),
    el("span", { class: "v" },
      `${b?.[itemKey] || 0} ${itemLabel} · ${b?.records || 0} records ` +
      `(A ${b?.records_a || 0} / B ${b?.records_b || 0})`),
  ];

  return el("details", { class: "gate evidence-strip" }, [
    el("summary", {}, [el("strong", {}, "Evidence "), summary]),
    el("div", { class: "gate-rows" }, [
      el("span", { class: "k" }, "Direct contact"),
      el("span", { class: "v" },
        `${d.records || 0} records (${d.calls || 0} calls, ${d.sms || 0} SMS · ` +
        `A→B ${d.a_to_b || 0} / B→A ${d.b_to_a || 0})`),
      ...row("Mutual calls · distinctive", mc.distinctive, "contacts", "contacts"),
      ...row("Mutual calls · common", mc.common, "contacts", "contacts"),
      ...row("Mutual locations · meet-up", ml.meet_up, "areas", "areas"),
      ...row("Mutual locations · shared-only", ml.non_meet_up, "areas", "areas"),
    ]),
  ]);
}
```

In `matchFindingsBlock`, after the dataset-mode note and BEFORE the caveats/findings:

```javascript
  const ev = evidenceCountsBlock(payload.evidence_counts);
  if (ev) block.appendChild(ev);
```

In `app.css`, beside the `.mode-note` rules:

```css
/* Evidence strip: raw tallies, never a verdict — muted, mono numbers, no pill. */
.evidence-strip { margin-top: var(--s3); }
.evidence-strip > summary { color: var(--fg); }
.evidence-strip > summary strong { color: var(--fg-muted); font-weight: 600; }
.evidence-strip .gate-rows .v { color: var(--fg-muted); }
```

- [ ] **Step 4: Run to verify they pass**

Run: `node --check app\web\js\components.js && node --test app\web\js\components.test.mjs`
Expected: PASS (24 tests)

- [ ] **Step 5: Commit**

```bash
git add app/web/js/components.js app/web/js/components.test.mjs app/web/css/app.css
git commit -m "claude: evidence counters - matcher card strip + breakdown table"
```

---

### Task 4: "Evidence counts" export sheet + docs/fixture expectations

**Files:**
- Modify: `app/reporting/export.py` (new sheet + headers + row builder)
- Modify: `tests/phase2a/test_matching.py` (export assertions)
- Modify: `docs/reference/api.md` (payload + workbook layout)
- Modify: `docs/matcher-test-scenarios.md`, `tools/gen_matcher_scenarios.py` (expected counts)
- Modify: `HANDOFF.md` (entry), `CLAUDE.md` (test count)

**Interfaces:**
- Consumes: the stored `result_json`'s `evidence_counts` (Task 2). Reads STORED data only — never recomputes.
- Produces: a sixth workbook sheet, `Evidence counts`, one row per saved pair.

- [ ] **Step 1: Write the failing test**

```python
def test_export_evidence_counts_sheet(client, pair):
    a, b = pair
    client.post("/api/match/save", json={"target_a_id": a, "target_b_id": b})
    wb = load_workbook(io.BytesIO(client.post("/api/export/results.xlsx").data))
    rows = list(wb["Evidence counts"].iter_rows(values_only=True))
    assert rows[0][:6] == ("Pair ID", "Dataset", "Target A", "Target B", "Saved at",
                           "Direct records")
    row = rows[1]
    assert "A (100)" in row[2] and "B (200)" in row[3]
    assert row[5] == 4                      # direct records
    assert row[10] == 3 and row[11] == 6    # distinctive contacts / records
    assert row[14] == 3                     # meet-up areas
    assert row[16] == 1 and row[17] == 2    # shared-only areas / records


def test_export_evidence_counts_placeholder_when_nothing_saved(client):
    wb = load_workbook(io.BytesIO(client.post("/api/export/results.xlsx").data))
    rows = list(wb["Evidence counts"].iter_rows(values_only=True))
    assert rows[1][0] == "none saved"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests\phase2a\test_matching.py -q -k evidence_counts_sheet`
Expected: FAIL — `KeyError: 'Evidence counts'` (no such sheet)

- [ ] **Step 3: Implement**

In `export.py`, add the headers next to the others:

```python
COUNTS_HEADERS = ["Pair ID", "Dataset", "Target A", "Target B", "Saved at",
                  "Direct records", "Calls", "SMS", "A→B", "B→A",
                  "Shared contacts (distinctive)", "Mutual-call records (distinctive)",
                  "Shared contacts (common)", "Mutual-call records (common)",
                  "Meet-up areas", "Meet-up records",
                  "Shared-only areas", "Shared-only records"]
```

and the row builder:

```python
def _append_counts_row(ws, saved: dict) -> None:
    """One row per saved pair: the RAW evidence tallies (no confidence anywhere --
    a count is not a gated verdict). Rows saved before the counters existed carry
    no evidence_counts: emit em-dashes rather than inventing zeros, which would
    read as 'no evidence' instead of 'not measured'."""
    result = saved["result"]
    pair = result.get("pair") or {}
    base = [saved["id"], saved.get("dataset_name"),
            _target_cell(pair.get("target_a") or {}),
            _target_cell(pair.get("target_b") or {}),
            _fmt_when(saved.get("created_at"))]
    counts = result.get("evidence_counts")
    if not counts:
        ws.append(base + ["—"] * (len(COUNTS_HEADERS) - len(base)))
        ws.cell(row=ws.max_row, column=6).font = _NOT_ANALYZED_FONT
        return
    d = counts.get("direct") or {}
    mc = counts.get("mutual_calls") or {}
    ml = counts.get("mutual_locations") or {}

    def cells(bucket, item_key):
        b = bucket or {}
        return [b.get(item_key, 0), b.get("records", 0)]

    ws.append(base + [
        d.get("records", 0), d.get("calls", 0), d.get("sms", 0),
        d.get("a_to_b", 0), d.get("b_to_a", 0),
        *cells(mc.get("distinctive"), "contacts"),
        *cells(mc.get("common"), "contacts"),
        *cells(ml.get("meet_up"), "areas"),
        *cells(ml.get("non_meet_up"), "areas"),
    ])
```

In `build_results_workbook`: create the sheet (`counts_ws = wb.create_sheet("Evidence counts")`), append `COUNTS_HEADERS`, loop `for saved in pair_matches: _append_counts_row(counts_ws, saved)`, add the `_placeholder(counts_ws, "none saved")` when `pair_matches` is empty, and include `counts_ws` in the `_finish_sheet` loop. Update the module docstring ("Layout: six sheets…").

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests\phase2a tests\architecture phase1_cdr\tests -q`
Expected: PASS

- [ ] **Step 5: Update docs + fixture expectations**

- `docs/reference/api.md`: add `evidence_counts` to the payload jsonc block (copy the shape from the spec) and mention the sixth sheet in the export paragraph.
- `tools/gen_matcher_scenarios.py`: assert the counts for two scenario pairs (P01 all-evidence, P15 shared-only-area) inside `verify()`, so the fixture can never drift from the counter.
- `docs/matcher-test-scenarios.md`: note the evidence strip and the new sheet.
- `HANDOFF.md`: new top entry (what shipped, that counts carry no confidence by design, the disjoint-by-area rule, and that pre-existing saved pairs export em-dashes until re-saved).
- `CLAUDE.md`: bump the passing-test count.

- [ ] **Step 6: Full verification**

Run:
```
.venv\Scripts\python.exe -m pytest tests\phase2a tests\architecture phase1_cdr\tests -q
.venv\Scripts\python.exe -m ruff check app tests main.py tools
.venv\Scripts\python.exe tools\gen_matcher_scenarios.py
node --test app\web\js\components.test.mjs
git diff --stat main -- phase1_cdr/
```
Expected: all green; the phase1 diff EMPTY.

- [ ] **Step 7: Commit + push**

```bash
git add app/reporting/export.py tests/phase2a/test_matching.py docs/ tools/ HANDOFF.md CLAUDE.md
git commit -m "claude: evidence counters - export sheet + docs"
git push origin claude/contact-matcher
```
