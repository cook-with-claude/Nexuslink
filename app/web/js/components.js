// Shared UI bits. Single source of truth for the confidence pill and the gate
// trace, so the "no raw JSON / one visual language" rules hold everywhere.

import { callTypeDisplay } from "./call-types.js";

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
  info: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z M12 16v-4 M12 8h.01",
  check: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z M8 12l2.5 2.5L16 9",
  circle: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z",
  table: "M3 4h18v16H3z M3 10h18 M9 10v10 M15 10v10",
  download: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4 M7 10l5 5 5-5 M12 15V3",
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
      // Nested buttons/links keep their own keyboard behavior.
      if (e.target !== tr) return;
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

// --- binding gates (what caps the weakest-link confidence) ---
// The headline confidence is min() across the four gates (frozen Phase 1), so it
// discards HOW MANY gates sit at the floor: "one Low, three High" (a single
// fixable weakness) and "all four Low" (hopeless) both render as "Low". This
// surfaces the binding gate(s) + their count next to the pill so the headline
// stops throwing away the gate vector. Presentation only — `gates` is already on
// the result (bridge.py serializes r.gates). See GitHub #10 (refines #2).
const GATE_SHORT = {
  N: "sample size",
  share: "dominance",
  closeness: "separation",
  density: "coverage",
};
const BINDING_ORDER = ["N", "share", "closeness", "density"];

// Which gate(s) hold the result at its headline level, or null when the notion
// does not apply (empty window → no gates; a High result → every gate is High,
// nothing caps it; a tally → no 4-gate dict).
export function bindingGates(result) {
  const gates = result && result.gates;
  if (!gates) return null;
  const present = BINDING_ORDER.filter((k) => gates[k] !== undefined);
  if (present.length === 0) return null;
  const level = result.confidence; // the min() headline
  if (level === "High") return null; // all gates High — nothing is limiting it
  const binding = present.filter((k) => gates[k] === level);
  if (binding.length === 0) return null; // headline not among the gates (shouldn't happen)
  return { level, binding, total: present.length };
}

export function bindingNote(result) {
  const b = bindingGates(result);
  if (!b) return null;
  const names = b.binding.map((k) => GATE_SHORT[k]).join(", ");
  let text;
  if (b.binding.length === 1) {
    text = `Held at ${b.level} by one gate: ${names}.`;
  } else if (b.binding.length === b.total) {
    text = `Held at ${b.level} by all ${b.total} gates: ${names}.`;
  } else {
    text = `Held at ${b.level} by ${b.binding.length} of ${b.total} gates: ${names}.`;
  }
  return el("p", { class: "binding-note" }, text);
}

// --- detection renderers (shared by the Results screen and the Spreadsheet
// detection panel, which show the SAME home/work card + frequent-areas card in
// two different wrappers). Kept here so the two can't drift — GitHub #16. #10 had
// to be applied to both copies, which is exactly the maintenance tax this removes.
export function pct(share) {
  const n = Number(share);
  if (!Number.isFinite(n)) return "—";
  return (n * 100).toFixed(1) + "%";
}

// One home/work detection card: pill, area, binding-gate note, alternatives, gate
// trace. `wrapClass` is the ONLY thing that differed between the two screens
// (".card" on Results, ".det-block" in the Spreadsheet panel).
export function detectionBlock(title, r, wrapClass = "card") {
  const block = el("div", { class: wrapClass }, [
    el("div", { class: "card-head" }, [el("h3", {}, title), confidencePill(r)]),
    el("div", { class: "result-area mono" }, (r && r.area) ? r.area : "—"),
  ]);
  const bn = bindingNote(r);
  if (bn) block.appendChild(bn);
  if (r && r.alternatives && r.alternatives.length) {
    block.appendChild(el("div", { class: "alts" }, [
      "alternatives: ",
      ...r.alternatives.flatMap((a, i) => [i ? ", " : "", el("span", { class: "mono" }, a)]),
    ]));
  }
  block.appendChild(gateTrace(r));
  return block;
}

// The frequent-areas card: a plain count, NO confidence pill (a frequency table is
// a description, not a gated verdict) — only a descriptive sample-size note.
export function frequentAreasBlock(areas, conf, wrapClass = "card") {
  const block = el("div", { class: wrapClass });
  block.appendChild(el("div", { class: "card-head" }, [
    el("h3", {}, "Frequent areas"),
    el("span", { class: "kicker" }, "count, not a verdict"),
  ]));
  if (!areas || areas.length === 0) {
    block.appendChild(el("div", { class: "empty" }, "No area activity."));
    return block;
  }
  const note = sampleNote(areas, conf);
  if (note) block.appendChild(note);
  block.appendChild(el("table", {}, [
    el("thead", {}, el("tr", {}, [
      el("th", {}, "Area"), el("th", { class: "num" }, "Count"), el("th", { class: "num" }, "Share"),
    ])),
    el("tbody", {}, areas.map((a) => el("tr", {}, [
      el("td", { class: "data" }, a.area),
      el("td", { class: "num" }, String(a.count)),
      el("td", { class: "num dim" }, pct(a.share)),
    ]))),
  ]));
  return block;
}

// --- contact-matcher renderers ---
// Typed findings, each an expandable <details>: the summary row is label +
// strength pill + headline, the body is which gate(s) bound the weakest-link
// rating plus the evidence for that finding type. Strength reuses the
// confidence-pill classes deliberately: the matcher IS a gated inference
// (unlike the tallies, which carry no pill anywhere).

export function strengthPill(strength) {
  const cls = PILL_CLASS[strength] || "pill-insufficient";
  return el("span", { class: "pill " + cls }, strength || "n/a");
}

function kvRows(pairs) {
  return el("div", { class: "gate-rows" }, pairs.flatMap(([k, v]) => [
    el("span", { class: "k" }, k), el("span", { class: "v" }, String(v ?? "—")),
  ]));
}

// Evidence tables are capped: a real pair can produce hundreds of co-presence
// events (Phase-1's 6-month sample yields ~100 for two users), and dumping them
// all makes the card scroll for pages. The count is already in the headline; the
// table is a sample, so say so rather than pretending it's the whole list.
const EVIDENCE_ROW_CAP = 20;

function capped(rows) {
  return { shown: rows.slice(0, EVIDENCE_ROW_CAP), hidden: Math.max(0, rows.length - EVIDENCE_ROW_CAP) };
}

function moreNote(hidden) {
  if (!hidden) return null;
  // Deliberately does NOT say "see the export" — the export's evidence cell is a
  // digest too. The headline carries the complete count; this table is a sample.
  return el("p", { class: "hint" }, `… and ${hidden} more (the headline count is the total).`);
}

function findingEvidence(f, pair) {
  const ev = f.evidence || {};
  const nameA = pair.target_a.name;
  const nameB = pair.target_b.name;
  if (f.type === "direct_contact") {
    return [kvRows([
      ["Total", ev.total], ["Calls", ev.calls], ["SMS", ev.sms],
      [`${nameA} → ${nameB}`, ev.a_to_b], [`${nameB} → ${nameA}`, ev.b_to_a],
      ["First", ev.first || "—"], ["Last", ev.last || "—"],
    ])];
  }
  if (f.type === "mutual_contacts") {
    const { shown, hidden } = capped(ev.shared_contacts || []);
    return [
      kvRows(Object.entries(ev.gates || {}).map(([k, v]) => ["gate: " + k, v])),
      el("table", {}, [
        el("thead", {}, el("tr", {}, [
          el("th", {}, "Contact"), el("th", { class: "num" }, nameA + " ×"),
          el("th", { class: "num" }, nameB + " ×"),
          el("th", { class: "num" }, "Others with it"), el("th", {}, "Distinctive"),
        ])),
        el("tbody", {}, shown.map((c) => el("tr", {}, [
          el("td", { class: "data" }, c.party),
          el("td", { class: "num" }, String(c.count_a)),
          el("td", { class: "num" }, String(c.count_b)),
          el("td", { class: "num dim" }, String(c.other_users_with)),
          el("td", { class: "dim" }, c.distinctive ? "yes" : "no (common)"),
        ]))),
      ]),
      moreNote(hidden),
    ];
  }
  if (f.type === "co_presence") {
    const { shown, hidden } = capped(ev.events || []);
    return [
      kvRows(Object.entries(ev.gates || {}).map(([k, v]) => ["gate: " + k, v])),
      el("table", {}, [
        el("thead", {}, el("tr", {}, [
          el("th", {}, "Area"), el("th", {}, "Day"),
          el("th", {}, nameA + " time"), el("th", {}, nameB + " time"),
          el("th", { class: "num" }, "Others seen there"),
        ])),
        el("tbody", {}, shown.map((e) => el("tr", {}, [
          el("td", { class: "data" }, e.area),
          el("td", { class: "data dim" }, e.day),
          el("td", { class: "data dim" }, String(e.a_time || "—").replace("T", " ")),
          el("td", { class: "data dim" }, String(e.b_time || "—").replace("T", " ")),
          el("td", { class: "num dim" }, String(e.other_users_with)),
        ]))),
      ]),
      moreNote(hidden),
    ];
  }
  return [];
}

// The full findings block for one pair-match payload (the /api/match response
// or a saved result_json). Used by the Spreadsheet matcher card; the export
// sheet carries the same stored content.
// The dataset-mode line (adaptive gates, spec 2026-07-13): which rule-set judged
// this pair and how decisively the dataset sits on its side of the boundary.
// The mode boundary is a cliff, so it is DISCLOSED with its own tier — and a
// dataset sitting on the line says "near tie" instead of silently flipping
// modes between imports. Old saved payloads without dataset_context render
// exactly as before (returns null).
export function datasetModeNote(ctx) {
  if (!ctx || !ctx.mode) return null;
  const label = ctx.mode === "close-knit"
    ? "Close-knit / interconnected dataset" : "Strangers dataset";
  if (ctx.classification === "Near tie") {
    return el("div", { class: "mode-note mode-near-tie" }, [
      el("strong", {}, "Near tie: "),
      `this dataset sits ON the strangers ↔ close-knit line ` +
      `(avg ${ctx.avg_shared_contacts_per_pair} shared contacts per pair vs ` +
      `boundary ${ctx.boundary}). Mutual-contact ratings may flip with small ` +
      `data changes.`,
    ]);
  }
  return el("div", { class: "mode-note" }, [
    el("strong", {}, label),
    ` — ${ctx.classification} confidence in this reading ` +
    `(avg ${ctx.avg_shared_contacts_per_pair} shared contacts per pair; ` +
    `boundary ${ctx.boundary}).`,
  ]);
}

export function matchFindingsBlock(payload, wrapClass = "det-block") {
  const block = el("div", { class: wrapClass });
  const modeNote = datasetModeNote(payload.dataset_context);
  if (modeNote) block.appendChild(modeNote);
  for (const c of payload.caveats || []) {
    block.appendChild(el("p", { class: "hint" }, "⚠ " + c));
  }
  if (!payload.findings || payload.findings.length === 0) {
    block.appendChild(el("div", { class: "empty" },
      "No link found between these targets."));
    return block;
  }
  for (const f of payload.findings) {
    const d = el("details", { class: "gate finding" }, [
      el("summary", {}, [
        el("strong", {}, f.label), " ", strengthPill(f.strength),
        " ", el("span", { class: "dim" }, f.headline),
      ]),
    ]);
    if (f.strength !== "High" && f.bound_by && f.bound_by.length) {
      d.appendChild(el("p", { class: "binding-note" },
        `Held at ${f.strength} by: ${f.bound_by.join(", ")}.`));
    }
    // Gate-cliff disclosure: a raw value sitting near a tier line is worth a
    // sentence — "Medium" alone hides whether it was 49-vs-50 or 20-vs-50.
    for (const n of f.notes || []) {
      d.appendChild(el("p", { class: "hint near-note" }, "≈ " + n));
    }
    findingEvidence(f, payload.pair)
      .filter((node) => node !== null)   // moreNote() is null when nothing is capped
      .forEach((node) => d.appendChild(node));
    block.appendChild(d);
  }
  const alone = (payload.details || {}).shared_areas_no_time_overlap || [];
  if (alone.length) {
    block.appendChild(el("p", { class: "hint" },
      `Also share ${alone.length} area(s) without time overlap ` +
      `(too weak to be a finding): ${alone.join(", ")}`));
  }
  return block;
}

// --- pair record ledger (spec 2026-07-13-pair-record-ledger-design.md) ---
// The RECORDS behind a pair, not a verdict about them: no strength pills, no
// gates, no confidence anywhere. Shows LEDGER_PAGE rows; an Expand control
// reveals the rest in a scrollable grid (a heavy pair runs to thousands of rows).
// The export is the exhaustive artifact — say so rather than implying rows are lost.

export const LEDGER_PAGE = 50;

// Sorting is client-side (the whole ledger is already in hand) but behaves like
// the records sheet's server-side sort: click a header to toggle, an arrow shows
// the active column and direction. Pure + exported so the ordering rules are
// testable without a DOM. `null` column = the natural order the server returned
// (grouped by category, then by time).
export function sortLedgerRows(rows, col, dir = "asc") {
  if (!col) return rows;
  const sign = dir === "desc" ? -1 : 1;
  const key = (r) => (col === "duration_seconds"
    ? Number(r.duration_seconds ?? 0)
    : String(r.timestamp ?? ""));
  return [...rows].sort((a, b) => {
    const ka = key(a);
    const kb = key(b);
    if (ka < kb) return -1 * sign;
    if (ka > kb) return 1 * sign;
    return 0;
  });
}

function ledgerCell(r) {
  const party = r.other_party_is_target
    ? `${r.other_party_name} (${r.other_party})`
    : (r.other_party || "—");
  const distinctive = r.distinctive === null || r.distinctive === undefined
    ? "—" : (r.distinctive ? "distinctive" : "common");
  return [
    el("td", {}, r.category_label),
    el("td", { class: "data" }, `${r.who} (${r.who_phone})`),
    el("td", { class: "data dim" }, String(r.timestamp || "").replace("T", " ")),
    el("td", { class: "dim" }, callTypeDisplay(r.call_type)),
    el("td", { class: "num dim" }, String(r.duration_seconds ?? 0)),
    el("td", { class: "data" }, [
      party,
      r.other_party_is_target
        ? el("span", { class: "tag tag-target" }, "target")
        : null,
    ].filter(Boolean)),
    el("td", { class: "data" }, r.area || "—"),
    el("td", { class: "dim" }, distinctive),
  ];
}

// Client-side filtering: the ledger's full row set is already in hand, so a
// filter is instant (no round trip, unlike the records sheet, which pages over a
// whole dataset server-side). Pure and exported so the matching rules are
// testable without a DOM. Text filters are case-insensitive "contains".
export function filterLedgerRows(rows, f = {}) {
  const has = (hay, needle) =>
    !needle || String(hay ?? "").toLowerCase().includes(needle.toLowerCase());
  return rows.filter((r) => {
    if (f.category && r.category !== f.category) return false;
    if (f.who && r.who_phone !== f.who) return false;
    if (f.call_type && String(r.call_type) !== String(f.call_type)) return false;
    if (f.distinctive === "distinctive" && r.distinctive !== true) return false;
    if (f.distinctive === "common" && r.distinctive !== false) return false;
    if (f.distinctive === "na" && r.distinctive !== null
        && r.distinctive !== undefined) return false;
    if (f.targets_only && !r.other_party_is_target) return false;
    if (!has(r.timestamp, f.when)) return false;
    if (!has(r.area, f.area)) return false;
    // party matches the number OR the target name, so "carlos" finds his rows
    if (f.party && !(has(r.other_party, f.party) || has(r.other_party_name, f.party))) {
      return false;
    }
    return true;
  });
}

export function ledgerTable(payload) {
  const block = el("div", {});
  const all = (payload && payload.rows) || [];
  if (all.length === 0) {
    block.appendChild(el("div", { class: "empty" },
      "No records link these two targets."));
    return block;
  }

  const counts = payload.category_counts || {};
  block.appendChild(el("p", { class: "hint" },
    `${payload.row_count} record(s): ` +
    Object.entries(counts).map(([k, v]) => `${v} ${k.replace(/_/g, " ")}`).join(" · ")));

  // --- column filters, in the header row (the records sheet's pattern) ---
  const cats = [...new Set(all.map((r) => r.category))];
  const fCat = el("select", { class: "col-filter", "aria-label": "filter category" },
    [el("option", { value: "" }, "All")].concat(cats.map((c) =>
      el("option", { value: c }, (all.find((r) => r.category === c) || {}).category_label))));
  const whos = [...new Set(all.map((r) => r.who_phone))];
  const fWho = el("select", { class: "col-filter", "aria-label": "filter who" },
    [el("option", { value: "" }, "Both")].concat(whos.map((p) =>
      el("option", { value: p }, (all.find((r) => r.who_phone === p) || {}).who))));
  const fWhen = el("input", { class: "col-filter", type: "text",
    placeholder: "2026-05-03…", "aria-label": "filter date" });
  const types = [...new Set(all.map((r) => r.call_type))];
  const fType = el("select", { class: "col-filter", "aria-label": "filter type" },
    [el("option", { value: "" }, "Any")].concat(types.map((t) =>
      el("option", { value: String(t) }, callTypeDisplay(t)))));
  const fParty = el("input", { class: "col-filter", type: "text",
    placeholder: "number or name…", "aria-label": "filter other party" });
  const fArea = el("input", { class: "col-filter", type: "text",
    placeholder: "contains…", "aria-label": "filter area" });
  const fDist = el("select", { class: "col-filter", "aria-label": "filter distinctive" }, [
    el("option", { value: "" }, "Any"),
    el("option", { value: "distinctive" }, "distinctive"),
    el("option", { value: "common" }, "common"),
    el("option", { value: "na" }, "—"),
  ]);
  const controls = [fCat, fWho, fWhen, fType, fParty, fArea, fDist];

  // Sortable headers (the records sheet's affordance): click toggles
  // oldest/newest and shortest/longest; the arrow marks the active column.
  let sortCol = "timestamp";
  let sortDir = "asc";
  const whenBtn = el("button", { class: "link", title: "Sort by time" }, "Date & time");
  const durBtn = el("button", { class: "link", title: "Sort by duration" }, "Duration");
  const sortMark = (col) => (sortCol !== col ? "" : (sortDir === "asc" ? " ↑" : " ↓"));

  const body = el("tbody", {});
  const wrap = el("div", { class: "ledger-scroll" }, el("table", { class: "ledger-table" }, [
    el("thead", {}, [
      el("tr", {}, [
        el("th", {}, "Category"), el("th", {}, "Who"), el("th", {}, whenBtn),
        el("th", {}, "Type"), el("th", { class: "num" }, durBtn),
        el("th", {}, "Other party"), el("th", {}, "Area"), el("th", {}, "Distinctive"),
      ]),
      el("tr", { class: "filter-row" }, [
        el("th", {}, fCat), el("th", {}, fWho), el("th", {}, fWhen),
        el("th", {}, fType), el("th", {}),          // duration: nothing to filter
        el("th", {}, fParty), el("th", {}, fArea), el("th", {}, fDist),
      ]),
    ]),
    body,
  ]));
  block.appendChild(wrap);

  const note = el("p", { class: "hint" }, "");
  const expand = el("button", { class: "btn btn-sm" }, "Expand all");
  const actions = el("div", { class: "form-actions" }, [expand, note]);
  block.appendChild(actions);

  let expanded = false;
  const render = () => {
    const rows = sortLedgerRows(filterLedgerRows(all, {
      category: fCat.value, who: fWho.value, when: fWhen.value,
      call_type: fType.value, party: fParty.value, area: fArea.value,
      distinctive: fDist.value,
    }), sortCol, sortDir);
    const shown = expanded ? rows.length : Math.min(LEDGER_PAGE, rows.length);
    clear(body);
    for (const r of rows.slice(0, shown)) body.appendChild(el("tr", {}, ledgerCell(r)));
    whenBtn.textContent = "Date & time" + sortMark("timestamp");
    durBtn.textContent = "Duration" + sortMark("duration_seconds");

    const filtered = rows.length !== all.length ? ` (filtered from ${all.length})` : "";
    if (rows.length === 0) {
      note.textContent = "No records match the current filter.";
    } else if (shown < rows.length) {
      note.textContent = `Showing the first ${shown} of ${rows.length}${filtered}. ` +
        "The export contains every record.";
    } else {
      note.textContent = `Showing all ${rows.length} record(s)${filtered}.`;
    }
    // The Expand control only means something while rows are still withheld.
    expand.disabled = expanded || rows.length <= LEDGER_PAGE;
  };

  expand.addEventListener("click", () => {
    expanded = true;
    wrap.classList.add("expanded");
    render();
  });
  const toggleSort = (col) => () => {
    // Same toggle rule as the records sheet: a new column starts ascending; the
    // active column flips direction.
    sortDir = sortCol === col && sortDir === "asc" ? "desc" : "asc";
    sortCol = col;
    render();
  };
  whenBtn.addEventListener("click", toggleSort("timestamp"));
  durBtn.addEventListener("click", toggleSort("duration_seconds"));
  for (const c of controls) {
    c.addEventListener("input", render);
    c.addEventListener("change", render);
  }
  render();
  return block;
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

// --- sample size (data sufficiency for descriptive tallies) ---
// A frequency ranking is a description, not a gated inference, so it carries no
// confidence — BUT any tally over too few records is still shaky. The honest
// sufficiency signal is N itself (the share gate is a pure ratio, so it would
// rate "100% of 3 records" as High). We surface N descriptively, never as a pill.

export function sampleSize(areas, conf) {
  // Prefer the stored frequent-areas confidence's window total (this is the one
  // consumer of that otherwise-unused field); fall back to deriving N from the
  // top area's count/share for older stored results that lack it.
  if (conf && Number.isFinite(conf.total_window_records)) return conf.total_window_records;
  const top = (areas || [])[0];
  if (top && top.share > 0) return Math.round(top.count / top.share);
  return null;
}

export function sampleNote(areas, conf) {
  const n = sampleSize(areas, conf);
  if (n === null) return null;
  // State N plainly and let the number speak — no invented "thin data" cutoff,
  // which would just be another ungrounded gate. The count is the whole signal.
  return el("p", { class: "hint sample-note" },
    `Ranking of ${n} record${n === 1 ? "" : "s"} — read the shares to judge how firm it is.`);
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
