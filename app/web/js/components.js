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

// --- inline SVG icons (Lucide-style stroke paths; no emoji, one consistent set) ---
// el() uses createElement, which can't build SVG nodes, so icons get their own
// namespaced builder. Each entry is one path `d` (multiple subpaths allowed).
const SVG_NS = "http://www.w3.org/2000/svg";
const ICONS = {
  dashboard: "M3 3h7v9H3z M14 3h7v5h-7z M14 12h7v9h-7z M3 16h7v5H3z",
  database: "M12 8c4.97 0 9-1.34 9-3s-4.03-3-9-3-9 1.34-9 3 4.03 3 9 3z M3 5v14c0 1.66 4.03 3 9 3s9-1.34 9-3V5 M3 12c0 1.66 4.03 3 9 3s9-1.34 9-3",
  lock: "M5 11h14v10H5z M8 11V7a4 4 0 0 1 8 0v4",
  logout: "M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4 M16 17l5-5-5-5 M21 12H9",
  command: "M9 6a3 3 0 1 0-3 3h12a3 3 0 1 0-3-3v12a3 3 0 1 0 3-3H6a3 3 0 1 0 3 3z",
  panel: "M3 4h18v16H3z M9 4v16",
  back: "M19 12H5 M12 19l-7-7 7-7",
  upload: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4 M17 8l-5-5-5 5 M12 3v12",
};

export function icon(name, size = 16) {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("width", String(size));
  svg.setAttribute("height", String(size));
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "2");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("class", "icon");
  const p = document.createElementNS(SVG_NS, "path");
  p.setAttribute("d", ICONS[name] || "");
  svg.appendChild(p);
  return svg;
}

// --- keyboard-navigable table rows ---
// Makes every `tr.clickable` inside a tbody focusable and operable without a
// mouse: Tab to a row, Enter/Space activates (fires its click), Up/Down moves
// focus between rows. Apply after the rows are appended.
export function navigableRows(tbody) {
  const all = () => Array.from(tbody.querySelectorAll("tr.clickable"));
  for (const tr of all()) {
    tr.setAttribute("tabindex", "0");
    tr.setAttribute("role", "button");
    tr.addEventListener("keydown", (e) => {
      const rows = all();
      const i = rows.indexOf(tr);
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); tr.click(); }
      else if (e.key === "ArrowDown") { e.preventDefault(); (rows[i + 1] || rows[0]).focus(); }
      else if (e.key === "ArrowUp") { e.preventDefault(); (rows[i - 1] || rows[rows.length - 1]).focus(); }
    });
  }
  return tbody;
}

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
  const t = el("div", { class: "toast toast-" + kind, role: "alert" }, message);
  root.appendChild(t);
  setTimeout(() => t.remove(), 3200);
}

// --- message banners ---
// Errors announce assertively (role=alert); confirmations announce politely.
export function msg(text, kind = "error") {
  return el("div", { class: "msg msg-" + kind, role: kind === "error" ? "alert" : "status" }, text);
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
