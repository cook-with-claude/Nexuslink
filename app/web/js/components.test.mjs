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

// --- minimal DOM shim: only what el("p", {class}, "text") exercises ---
globalThis.document = {
  createTextNode: (s) => ({ nodeType: 3, textContent: String(s) }),
  createElement: (tag) => ({
    tag,
    className: "",
    _children: [],
    setAttribute() {},
    addEventListener() {},
    appendChild(c) { this._children.push(c); return c; },
    get textContent() { return this._children.map((c) => c.textContent).join(""); },
  }),
};

const { bindingGates, bindingNote, detectionBlock, frequentAreasBlock,
        strengthPill, matchFindingsBlock } = await import("./components.js");

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
