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

const { bindingGates, bindingNote } = await import("./components.js");

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
