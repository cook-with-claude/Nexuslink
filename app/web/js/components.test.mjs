// Behavioural coverage for the binding-gate note (GitHub #10).
//
// The SPA is vanilla no-build JS with no test framework by design, so this uses
// ONLY Node's built-in runner (`node --test`) and `node:assert` — no npm, no
// package.json, nothing to install. It stubs the minimal `document` surface that
// el() touches (createElement/createTextNode) so the real components.js runs
// unmodified. CI runs it in the `frontend` job alongside `node --check`.
//
// Why this is worth a test when the rest of the SPA is check-only: bindingGates()
// is the one piece of frontend logic that re-derives a decision from the frozen
// Phase 1 gate vector (which gate(s) equal the min() headline, and how many). The
// branch table below is the contract — a copy or suppression regression here
// would silently mislead about *why* a detection is weak.

import { test } from "node:test";
import assert from "node:assert/strict";

// --- minimal DOM shim ---
// Covers what el() touches, plus the little more the ledger table needs:
// clear() (firstChild/removeChild), classList, remove(), and dispatchable click
// handlers so the "Expand all" behaviour can actually be exercised.
globalThis.document = {
  createTextNode: (s) => ({ nodeType: 3, textContent: String(s) }),
  createElement: (tag) => ({
    tag,
    className: "",
    _children: [],
    _listeners: {},
    _parent: null,
    classList: {
      _set: new Set(),
      add(c) { this._set.add(c); },
      contains(c) { return this._set.has(c); },
    },
    setAttribute() {},
    addEventListener(type, fn) { (this._listeners[type] ||= []).push(fn); },
    click() { for (const fn of this._listeners.click || []) fn(); },
    appendChild(c) { c._parent = this; this._children.push(c); return c; },
    removeChild(c) { this._children = this._children.filter((x) => x !== c); return c; },
    remove() { if (this._parent) this._parent.removeChild(this); },
    get firstChild() { return this._children[0] || null; },
    get textContent() { return this._children.map((c) => c.textContent).join(""); },
    set textContent(v) { this._children = [{ nodeType: 3, textContent: String(v) }]; },
  }),
};

// Depth-first search of the shim tree (the real DOM's querySelector equivalent).
function findAll(node, pred, out = []) {
  if (pred(node)) out.push(node);
  for (const c of node._children || []) findAll(c, pred, out);
  return out;
}

const { bindingGates, bindingNote, detectionBlock, frequentAreasBlock,
        strengthPill, matchFindingsBlock, ledgerTable, filterLedgerRows,
        LEDGER_PAGE } = await import("./components.js");

const noteText = (result) => {
  const p = bindingNote(result);
  return p === null ? null : p.textContent;
};

// gates dict as the frozen detector emits it (each ∈ High/Medium/Low); the
// headline `confidence` is min() across the four, so it is always one of them.
const G = (n, share, closeness, density) => ({ N: n, share, closeness, density });

test("suppressed when nothing caps the result (all gates High → High)", () => {
  const r = { confidence: "High", gates: G("High", "High", "High", "High") };
  assert.equal(bindingGates(r), null);
  assert.equal(noteText(r), null);
});

test("single binding gate names that one gate", () => {
  const r = { confidence: "Low", gates: G("High", "High", "Low", "High") };
  assert.deepEqual(bindingGates(r), { level: "Low", binding: ["closeness"], total: 4 });
  assert.equal(noteText(r), "Held at Low by one gate: separation.");
});

test("single binding gate at Medium (level is carried through, not hard-coded)", () => {
  const r = { confidence: "Medium", gates: G("High", "Medium", "High", "High") };
  assert.equal(noteText(r), "Held at Medium by one gate: dominance.");
});

test("partial binding reports N of 4 in fixed gate order", () => {
  const r = { confidence: "Low", gates: G("Low", "High", "Low", "High") };
  assert.deepEqual(bindingGates(r).binding, ["N", "closeness"]);
  assert.equal(noteText(r), "Held at Low by 2 of 4 gates: sample size, separation.");
});

test("all four binding uses the 'all' phrasing", () => {
  const r = { confidence: "Low", gates: G("Low", "Low", "Low", "Low") };
  assert.equal(
    noteText(r),
    "Held at Low by all 4 gates: sample size, dominance, separation, coverage.",
  );
});

test("empty window (gates null → Insufficient data) is suppressed", () => {
  const r = { confidence: "Insufficient data", gates: null };
  assert.equal(bindingGates(r), null);
  assert.equal(noteText(r), null);
});

test("missing gates key and null result are suppressed (defensive)", () => {
  assert.equal(bindingGates({ confidence: "Low" }), null);
  assert.equal(bindingGates(null), null);
  assert.equal(noteText(null), null);
});

// --- shared detection renderers (GitHub #16) ---
// The Results screen and the Spreadsheet panel render these SAME two cards; they
// differ only by the wrapper class. These smoke tests lock the wrapper param and
// the content so the two screens can't drift the way they did before the merge.

test("detectionBlock wrapper class is the only per-screen difference", () => {
  const r = { confidence: "Low", confidence_label: "Low",
    area: "Hamra", gates: G("High", "High", "Low", "High"), alternatives: [] };
  assert.equal(detectionBlock("Home", r).className, "card");              // Results default
  assert.equal(detectionBlock("Home", r, "det-block").className, "det-block"); // Spreadsheet
});

test("detectionBlock renders title, area, and the binding-gate note", () => {
  const r = { confidence: "Low", confidence_label: "Low",
    area: "Hamra", gates: G("High", "High", "Low", "High"), alternatives: [] };
  const text = detectionBlock("Work", r).textContent;
  assert.match(text, /Work/);
  assert.match(text, /Hamra/);
  assert.match(text, /Held at Low by one gate: separation\./);
});

test("frequentAreasBlock: empty vs ranked, and wrapper class", () => {
  assert.match(frequentAreasBlock([], null).textContent, /No area activity\./);
  const areas = [{ area: "Hamra", count: 12, share: 0.5 }];
  const block = frequentAreasBlock(areas, null, "det-block");
  assert.equal(block.className, "det-block");
  assert.match(block.textContent, /Hamra/);
  assert.match(block.textContent, /50\.0%/);   // pct() formatting
});

// --- contact-matcher renderers ---
// matchFindingsBlock renders the /api/match payload (and saved result_json —
// same shape). The rules locked here: strength reuses the confidence-pill
// classes; a bound_by note appears only below High; no-link and the
// shared-areas-without-time-overlap DETAIL line render as text, not findings.

const PAIR = {
  dataset_id: 1,
  target_a: { id: 1, name: "A", phone_number: "100" },
  target_b: { id: 2, name: "B", phone_number: "200" },
};

const FINDING = (over = {}) => ({
  type: "direct_contact", label: "Direct contact", strength: "High",
  bound_by: ["direct volume"], headline: "4× (2 calls, 2 SMS, both directions)",
  evidence: { total: 4, calls: 2, sms: 2, a_to_b: 2, b_to_a: 2,
              first: "2026-01-01T09:00:00", last: "2026-01-04T10:00:00" },
  ...over,
});

test("strengthPill maps strengths onto the confidence pill classes", () => {
  assert.equal(strengthPill("High").className, "pill pill-high");
  assert.equal(strengthPill("Low").className, "pill pill-low");
  assert.equal(strengthPill(undefined).className, "pill pill-insufficient");
});

test("matchFindingsBlock: no findings renders the no-link message + caveats", () => {
  const block = matchFindingsBlock({
    pair: PAIR, findings: [], no_link: true,
    caveats: ["The two observation windows overlap only 4%; absence of overlap is not meaningful."],
    details: { shared_areas_no_time_overlap: [] },
  });
  assert.match(block.textContent, /No link found between these targets\./);
  assert.match(block.textContent, /overlap only 4%/);
});

test("matchFindingsBlock: a High finding carries no bound_by note", () => {
  const block = matchFindingsBlock({
    pair: PAIR, findings: [FINDING()], caveats: [], details: {}, no_link: false,
  });
  assert.match(block.textContent, /Direct contact/);
  assert.match(block.textContent, /both directions/);
  assert.doesNotMatch(block.textContent, /Held at/);
});

test("matchFindingsBlock: a bound finding names its binding gates", () => {
  const block = matchFindingsBlock({
    pair: PAIR, caveats: [], no_link: false, details: {},
    findings: [FINDING({
      type: "mutual_contacts", label: "Mutual relationship", strength: "Low",
      bound_by: ["sample", "window overlap"],
      headline: "3 shared contacts",
      evidence: { gates: { sample: "Low" }, shared_contacts: [
        { party: "P1", count_a: 2, count_b: 1, other_users_with: 0, distinctive: true },
      ] },
    })],
  });
  assert.match(block.textContent, /Held at Low by: sample, window overlap\./);
  assert.match(block.textContent, /P1/);
  assert.match(block.textContent, /yes/);      // distinctive column
});

test("matchFindingsBlock: long evidence lists are capped with a '… and N more' note", () => {
  // A real 6-month pair yields ~100 co-presence events; rendering all of them
  // made the card scroll for pages. Cap at 20 and say how many were withheld —
  // and do NOT point at the export, whose evidence cell is a digest too.
  const events = Array.from({ length: 100 }, (_, i) => ({
    area: "Hamra", day: `2026-01-${String((i % 28) + 1).padStart(2, "0")}`,
    other_users_with: 3,
  }));
  const block = matchFindingsBlock({
    pair: PAIR, caveats: [], no_link: false, details: {},
    findings: [FINDING({
      type: "co_presence", label: "Meeting up", strength: "Low",
      bound_by: ["location distinctiveness"], headline: "100 co-located event(s)",
      evidence: { gates: { "event count": "High" }, events },
    })],
  });
  const rows = (block.textContent.match(/Hamra/g) || []).length;
  assert.equal(rows, 20);                                  // capped, not 100
  assert.match(block.textContent, /… and 80 more/);
  assert.doesNotMatch(block.textContent, /in the export/); // no false promise
});

test("matchFindingsBlock: a short evidence list gets no '…more' note", () => {
  const block = matchFindingsBlock({
    pair: PAIR, caveats: [], no_link: false, details: {},
    findings: [FINDING({
      type: "co_presence", label: "Meeting up", strength: "High", bound_by: [],
      headline: "2 events",
      evidence: { gates: {}, events: [
        { area: "Cafe", day: "2026-01-03", other_users_with: 0 },
        { area: "Edge", day: "2026-01-06", other_users_with: 0 },
      ] },
    })],
  });
  assert.doesNotMatch(block.textContent, /more/);
});

test("matchFindingsBlock: shared areas without time overlap are a detail line", () => {
  const block = matchFindingsBlock({
    pair: PAIR, findings: [FINDING()], caveats: [], no_link: false,
    details: { shared_areas_no_time_overlap: ["Far", "Airport"] },
  });
  assert.match(block.textContent, /too weak to be a finding/);
  assert.match(block.textContent, /Far, Airport/);
});

// Adaptive gates (spec 2026-07-13): the dataset-mode line and the gate-cliff
// near-boundary notes. Old saved payloads carry neither field and must render
// exactly as before.

test("matchFindingsBlock: dataset mode line renders with its confidence tier", () => {
  const block = matchFindingsBlock({
    pair: PAIR, findings: [FINDING()], caveats: [], no_link: false, details: {},
    dataset_context: { mode: "close-knit", classification: "High",
                       avg_shared_contacts_per_pair: 4.2, boundary: 2 },
  });
  assert.match(block.textContent, /Close-knit \/ interconnected dataset — High confidence/);
  assert.match(block.textContent, /avg 4.2 shared contacts per pair/);
});

test("matchFindingsBlock: a near-tie dataset says so instead of picking a side quietly", () => {
  const block = matchFindingsBlock({
    pair: PAIR, findings: [FINDING()], caveats: [], no_link: false, details: {},
    dataset_context: { mode: "strangers", classification: "Near tie",
                       avg_shared_contacts_per_pair: 1.9, boundary: 2 },
  });
  assert.match(block.textContent, /Near tie/);
  assert.match(block.textContent, /may flip with small data changes/);
});

test("matchFindingsBlock: near-boundary gate notes render under the finding", () => {
  const block = matchFindingsBlock({
    pair: PAIR, caveats: [], no_link: false, details: {},
    findings: [FINDING({
      strength: "Medium",
      notes: ["sample is just short of High: 49 vs 50"],
    })],
  });
  assert.match(block.textContent, /≈ sample is just short of High: 49 vs 50/);
});

test("matchFindingsBlock: payloads predating the adaptive gates render unchanged", () => {
  const block = matchFindingsBlock({
    pair: PAIR, findings: [FINDING()], caveats: [], no_link: false, details: {},
  });
  assert.doesNotMatch(block.textContent, /confidence in this reading/);
  assert.doesNotMatch(block.textContent, /≈/);
});

// --- pair record ledger: the records themselves, never a verdict ---

const LROW = (over = {}) => ({
  category: "shared_contact", category_label: "Shared contact",
  who: "A", who_phone: "100", timestamp: "2026-01-03T10:00:00",
  call_type: 1, duration_seconds: 60,
  other_party: "P1", other_party_name: null, other_party_is_target: false,
  area: "Home", distinctive: true, ...over,
});

const ledgerPayload = (rows) => ({
  pair: PAIR, rows, row_count: rows.length,
  category_counts: rows.reduce((m, r) => ({ ...m, [r.category]: (m[r.category] || 0) + 1 }), {}),
});

test("ledgerTable: renders record detail — date, time, type, party, area", () => {
  const block = ledgerTable(ledgerPayload([LROW()]));
  assert.match(block.textContent, /2026-01-03 10:00:00/);   // date AND time
  assert.match(block.textContent, /out call/);
  assert.match(block.textContent, /A \(100\)/);
  assert.match(block.textContent, /P1/);
  assert.match(block.textContent, /distinctive/);
});

test("ledgerTable: a common item is listed, not hidden — and labelled", () => {
  const block = ledgerTable(ledgerPayload([LROW({ other_party: "8880001", distinctive: false })]));
  assert.match(block.textContent, /8880001/);
  assert.match(block.textContent, /common/);
});

test("ledgerTable: a shared contact who is also a target is named and tagged", () => {
  const block = ledgerTable(ledgerPayload([LROW({
    other_party: "300", other_party_name: "Carlos", other_party_is_target: true,
  })]));
  assert.match(block.textContent, /Carlos \(300\)/);
  assert.match(block.textContent, /target/);
});

test("ledgerTable: direct rows show an em-dash for distinctive (not 'common')", () => {
  const block = ledgerTable(ledgerPayload([LROW({
    category: "direct", category_label: "Direct contact", distinctive: null,
    other_party: "200", other_party_name: "B", other_party_is_target: true,
  })]));
  // scope to the CELLS: the filter dropdown legitimately contains the word
  // "common" as one of its options, so a whole-block match would be meaningless
  const cells = findAll(block, (n) => n.tag === "td").map((c) => c.textContent);
  assert.ok(!cells.some((c) => c === "common"));
  assert.ok(cells.includes("—"));
});

test("ledgerTable: caps at LEDGER_PAGE rows and Expand all reveals the rest", () => {
  const rows = Array.from({ length: LEDGER_PAGE + 25 }, (_, i) =>
    LROW({ timestamp: `2026-01-01T10:${String(i % 60).padStart(2, "0")}:00` }));
  const block = ledgerTable(ledgerPayload(rows));
  // two header rows now: the column names and the filter row
  const bodyRows = () => findAll(block, (n) => n.tag === "tr").length - 2;
  assert.equal(bodyRows(), LEDGER_PAGE);
  assert.match(block.textContent, new RegExp(`first ${LEDGER_PAGE} of ${rows.length}`));
  assert.match(block.textContent, /export contains every record/);

  const expand = findAll(block, (n) => n.tag === "button")[0];
  expand.click();
  assert.equal(bodyRows(), rows.length);                    // every row now shown
  assert.match(block.textContent, new RegExp(`all ${rows.length} record`));
});

test("ledgerTable: renders a column filter row (the records sheet's pattern)", () => {
  const block = ledgerTable(ledgerPayload([
    LROW(), LROW({ category: "direct", category_label: "Direct contact" })]));
  const filterRow = findAll(block, (n) => (n.className || "") === "filter-row");
  assert.equal(filterRow.length, 1);
  const controls = findAll(block, (n) => (n.className || "") === "col-filter");
  assert.ok(controls.length >= 6);            // category, who, date, type, party, area, distinctive
});

// The filter rules are pure, so they are tested directly rather than through a
// DOM shim that would have to fake <select>.value.

const FROWS = [
  LROW({ category: "direct", who: "A", who_phone: "100", call_type: 1,
         other_party: "200", other_party_name: "B", other_party_is_target: true,
         area: "Home", distinctive: null, timestamp: "2026-01-01T09:00:00" }),
  LROW({ category: "shared_contact", who: "B", who_phone: "200", call_type: 11,
         other_party: "8880001", distinctive: false, area: "Bwork",
         timestamp: "2026-02-05T10:00:00" }),
  LROW({ category: "shared_location", who: "A", who_phone: "100", call_type: 1,
         other_party: null, area: "MALL", distinctive: true,
         timestamp: "2026-02-06T11:00:00" }),
];

test("filterLedgerRows: category, who and call type", () => {
  assert.equal(filterLedgerRows(FROWS, { category: "direct" }).length, 1);
  assert.equal(filterLedgerRows(FROWS, { who: "100" }).length, 2);
  assert.equal(filterLedgerRows(FROWS, { call_type: "11" }).length, 1);
  assert.equal(filterLedgerRows(FROWS, {}).length, 3);           // no filter = everything
});

test("filterLedgerRows: distinctive / common / not-applicable are separable", () => {
  assert.equal(filterLedgerRows(FROWS, { distinctive: "common" })[0].other_party, "8880001");
  assert.equal(filterLedgerRows(FROWS, { distinctive: "distinctive" })[0].area, "MALL");
  // "na" finds the direct rows, whose distinctive is null — NOT the common ones
  const na = filterLedgerRows(FROWS, { distinctive: "na" });
  assert.equal(na.length, 1);
  assert.equal(na[0].category, "direct");
});

test("filterLedgerRows: text filters are case-insensitive 'contains'", () => {
  assert.equal(filterLedgerRows(FROWS, { area: "mall" }).length, 1);
  assert.equal(filterLedgerRows(FROWS, { when: "2026-02" }).length, 2);   // month
  assert.equal(filterLedgerRows(FROWS, { party: "888" }).length, 1);
});

test("filterLedgerRows: the party filter matches a target NAME too", () => {
  // an analyst searching "b" should find the rows whose counterparty is target B
  const hits = filterLedgerRows(FROWS, { party: "B" });
  assert.equal(hits.length, 1);
  assert.equal(hits[0].other_party_name, "B");
});

test("ledgerTable: no strength pill anywhere — a record is not a verdict", () => {
  const block = ledgerTable(ledgerPayload([LROW(), LROW({ category: "direct" })]));
  const pills = findAll(block, (n) => (n.className || "").includes("pill"));
  assert.equal(pills.length, 0);
});

test("ledgerTable: an empty ledger says so", () => {
  const block = ledgerTable(ledgerPayload([]));
  assert.match(block.textContent, /No records link these two targets/);
});
