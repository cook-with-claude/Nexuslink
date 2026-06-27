// Shared UI bits. Single source of truth for the confidence pill and the gate
// trace, so the "no raw JSON / one visual language" rules hold everywhere.

// --- small DOM helpers ---
export function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null) continue;
    if (k === "class") node.className = v;
    // No innerHTML path on purpose: all backend strings (areas, phone numbers,
    // dataset names, skip reasons) render via textContent below, so there is no
    // XSS sink. Add text children, never raw HTML.
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const c of [].concat(children)) {
    if (c == null) continue;
    node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
  }
  return node;
}

export function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }

// --- confidence pill (4-state) ---
// API-MISMATCH #5: confidence has 4 states, not 3. "Insufficient data" renders
// as a muted/neutral pill (e.g. an empty home/work window).
const PILL_CLASS = {
  High: "pill-high",
  Medium: "pill-medium",
  Low: "pill-low",
  "Insufficient data": "pill-insufficient",
};

export function confidencePill(result) {
  if (!result) return el("span", { class: "pill pill-insufficient" }, "n/a");
  const cls = PILL_CLASS[result.confidence] || "pill-insufficient";
  // confidence_label already appends ": near tie" when applicable.
  return el("span", { class: "pill " + cls }, result.confidence_label || result.confidence);
}

// --- gate trace ---
// API-MISMATCH (brief constraint): NEVER dump raw JSON. Render the gates dict +
// numeric metrics as labeled rows inside a <details>, collapsed by default.
const GATE_META = [
  ["N", "Sample size (N)"],
  ["share", "Dominance (share)"],
  ["closeness", "Separation (closeness)"],
  ["density", "Coverage (density)"],
];
const NUM_META = [
  ["share", "share"],
  ["closeness", "closeness"],
  ["density", "density"],
];

function fmtNum(v) {
  if (v == null || v === "") return "—";
  const n = Number(v);
  return Number.isFinite(n) ? n.toFixed(3) : String(v);
}

export function gateTrace(result, summaryLabel = "Gate trace") {
  const rows = [];
  const gates = (result && result.gates) || {};
  for (const [key, label] of GATE_META) {
    if (gates[key] === undefined) continue;
    rows.push(el("span", { class: "k" }, label), el("span", { class: "v" }, String(gates[key])));
  }
  for (const [key, label] of NUM_META) {
    rows.push(el("span", { class: "k" }, label), el("span", { class: "v" }, fmtNum(result && result[key])));
  }
  if (result) {
    rows.push(
      el("span", { class: "k" }, "Records"),
      el("span", { class: "v" }, `${result.supporting_records} / ${result.total_window_records}`),
    );
  }
  return el("details", { class: "gate" }, [
    el("summary", {}, summaryLabel),
    el("div", { class: "gate-rows" }, rows),
  ]);
}

// --- inline confirm for destructive actions (no native confirm/alert) ---
export function confirmInline(triggerBtn, onConfirm, label = "Delete?") {
  const parent = triggerBtn.parentElement;
  const yes = el("button", { class: "btn btn-sm btn-danger", onclick: () => onConfirm() }, "Yes");
  const no = el("button", { class: "btn btn-sm" }, "No");
  const wrap = el("span", { class: "inline-confirm" }, [el("span", { class: "q" }, label), yes, no]);
  const restore = () => wrap.replaceWith(triggerBtn);
  no.addEventListener("click", restore);
  triggerBtn.replaceWith(wrap);
}

// --- toast ---
export function toast(message, kind = "ok") {
  const root = document.getElementById("toast-root");
  const t = el("div", { class: "toast toast-" + kind }, message);
  root.appendChild(t);
  setTimeout(() => t.remove(), 3200);
}

// --- message banners ---
export function msg(text, kind = "error") {
  return el("div", { class: "msg msg-" + kind }, text);
}

export function loading(text = "Loading…") {
  return el("div", { class: "loading" }, [el("span", { class: "spinner" }), text]);
}

// --- formatting ---
export function fmtDate(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  } catch {
    return iso;
  }
}
