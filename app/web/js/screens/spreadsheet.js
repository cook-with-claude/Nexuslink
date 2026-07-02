// SPREADSHEET. Three deliberately separated parts, because they answer
// different questions:
//   1. Records — read-only view of the imported rows, paged.
//   2. Detection — the confidence-gated INFERENCE. Always runs on the target's
//      FULL record set: the gates depend on sample size (N), so applying the
//      explorer's filters here would shrink N and produce wrong ratings.
//   3. Frequency explorer — a plain descriptive tally over the FILTERED slice.
//      No home/work labels and no confidence, by design: a count is not a
//      verdict, and filtering is legitimate here precisely because it's a tally.

import { api } from "../api.js";
import { shell } from "../layout.js";
import {
  el, loading, clear, msg, confidencePill, gateTrace,
} from "../components.js";
import { callTypeLabel, CALL_TYPE_OPTIONS } from "../call-types.js";

const PAGE_SIZE = 100;

export async function spreadsheetScreen(app) {
  const { page, setCrumb } = shell(app);
  setCrumb(["Spreadsheet"]);
  const body = el("div");
  body.appendChild(loading());
  page.appendChild(body);

  const [datasets, targets] = await Promise.all([api.datasets(), api.targets()]);
  clear(body);

  if (datasets.length === 0) {
    body.appendChild(el("div", { class: "card" },
      el("div", { class: "empty" }, "No datasets yet. Import a .xlsx first.")));
    return;
  }

  body.appendChild(recordsCard(datasets));
  body.appendChild(detectionCard(targets, datasets));
  body.appendChild(explorerCard(targets, datasets));
}

function targetOption(t, datasets) {
  const d = datasets.find((x) => x.id === t.dataset_id);
  return el("option", { value: String(t.id) },
    `${t.name} — ${t.phone_number}${d ? ` (${d.name})` : ""}`);
}

// ---- 1. records view ----

function recordsCard(datasets) {
  const card = el("div", { class: "card" });
  card.appendChild(el("div", { class: "card-head" }, [
    el("h3", {}, "Records"),
    el("span", { class: "kicker" }, "read-only view"),
  ]));

  const picker = el("select", { id: "ss-dataset" },
    datasets.map((d) => el("option", { value: String(d.id) }, `${d.name} (${d.row_count} rows)`)));
  card.appendChild(el("label", { for: "ss-dataset" }, "Dataset"));
  card.appendChild(picker);

  const slot = el("div");
  card.appendChild(slot);

  let offset = 0;
  const load = async () => {
    clear(slot);
    slot.appendChild(loading("Loading records…"));
    let res;
    try {
      res = await api.records(Number(picker.value), offset, PAGE_SIZE);
    } catch (e) {
      clear(slot);
      slot.appendChild(msg(e.message));
      return;
    }
    clear(slot);
    if (res.total === 0) {
      slot.appendChild(el("div", { class: "empty" }, "This dataset has no records."));
      return;
    }

    const rows = res.rows.map((r) => el("tr", {}, [
      el("td", { class: "data" }, r.phone_number),
      el("td", { class: "data dim" }, r.imei || "—"),
      el("td", { class: "data" }, r.area),
      el("td", { class: "data dim" }, r.timestamp),
      // Display label only (task: literate call types); the numeric code stays
      // the underlying value — surfaced in the tooltip.
      el("td", { title: "code " + r.call_type }, callTypeLabel(r.call_type)),
      el("td", { class: "num" }, String(r.duration_seconds)),
      el("td", { class: "data" }, r.other_party || "—"),
      el("td", { class: "data dim" }, r.other_imei || "—"),
      el("td", { class: "data dim" }, r.other_area || "—"),
    ]));
    slot.appendChild(el("div", { class: "table-scroll" }, el("table", {}, [
      el("thead", {}, el("tr", {}, [
        el("th", {}, "Phone"), el("th", {}, "IMEI"), el("th", {}, "Area"),
        el("th", {}, "Timestamp"), el("th", {}, "Type"),
        el("th", { class: "num" }, "Duration (s)"),
        el("th", {}, "Other party"), el("th", {}, "Other IMEI"), el("th", {}, "Other area"),
      ])),
      el("tbody", {}, rows),
    ])));

    const from = res.offset + 1;
    const to = res.offset + res.rows.length;
    const prev = el("button", { class: "btn btn-sm", disabled: res.offset === 0 ? "disabled" : null }, "‹ Prev");
    const next = el("button", { class: "btn btn-sm", disabled: to >= res.total ? "disabled" : null }, "Next ›");
    prev.addEventListener("click", () => { offset = Math.max(0, offset - PAGE_SIZE); load(); });
    next.addEventListener("click", () => { offset += PAGE_SIZE; load(); });
    slot.appendChild(el("div", { class: "pager" }, [
      prev, next, el("span", { class: "dim" }, `${from}–${to} of ${res.total} records`),
    ]));
  };

  picker.addEventListener("change", () => { offset = 0; load(); });
  load();
  return card;
}

// ---- 2. detection (full record set) ----

function detectionCard(targets, datasets) {
  const card = el("div", { class: "card card-inference" });
  card.appendChild(el("div", { class: "card-head" }, [
    el("h3", {}, "Detection"),
    el("span", { class: "kicker kicker-inference" }, "inference · full record set"),
  ]));
  card.appendChild(el("p", { class: "hint" },
    "Runs the confidence-gated detection on the target's complete record set. " +
    "The explorer filters below never apply here: the gates depend on sample size, " +
    "and a filtered subset would produce wrong ratings."));

  if (targets.length === 0) {
    card.appendChild(el("div", { class: "empty" }, "No targets yet. Add one from a dataset's Targets screen."));
    return card;
  }

  const picker = el("select", { id: "ss-det-target" },
    [el("option", { value: "" }, "— select a target —")]
      .concat(targets.map((t) => targetOption(t, datasets))));
  const btn = el("button", { class: "btn btn-primary" }, "Run detection");
  const slot = el("div");

  btn.addEventListener("click", async () => {
    clear(slot);
    if (!picker.value) { slot.appendChild(msg("Select a target.")); return; }
    btn.disabled = true;
    slot.appendChild(loading("Analyzing…"));
    try {
      const payload = await api.analyze(Number(picker.value));
      clear(slot);
      renderDetection(slot, payload);
    } catch (e) {
      clear(slot);
      slot.appendChild(msg(e.message));
    } finally {
      btn.disabled = false;
    }
  });

  card.appendChild(el("label", { for: "ss-det-target" }, "Target"));
  card.appendChild(picker);
  card.appendChild(el("div", { class: "form-actions" }, [btn]));
  card.appendChild(slot);
  return card;
}

// Same visual language as the RESULTS screen: confidencePill + gateTrace from
// components.js keep the "one visual language / no raw JSON" rules.
function renderDetection(slot, payload) {
  const block = (title, r) => {
    const b = el("div", { class: "det-block" }, [
      el("div", { class: "card-head" }, [el("h3", {}, title), confidencePill(r)]),
      el("div", { class: "result-area mono" }, (r && r.area) ? r.area : "—"),
    ]);
    if (r && r.alternatives && r.alternatives.length) {
      b.appendChild(el("div", { class: "alts" }, [
        "alternatives: ",
        ...r.alternatives.flatMap((a, i) => [i ? ", " : "", el("span", { class: "mono" }, a)]),
      ]));
    }
    b.appendChild(gateTrace(r));
    return b;
  };

  slot.appendChild(el("div", { class: "result-grid" }, [
    block("Home", payload.home),
    block("Work", payload.work),
  ]));

  const fa = el("div", { class: "det-block" });
  fa.appendChild(el("div", { class: "card-head" }, [
    el("h3", {}, "Frequent areas"),
    confidencePill(payload.frequent_areas_confidence),
  ]));
  const areas = payload.frequent_areas || [];
  if (areas.length === 0) {
    fa.appendChild(el("div", { class: "empty" }, "No area activity."));
  } else {
    fa.appendChild(el("table", {}, [
      el("thead", {}, el("tr", {}, [
        el("th", {}, "Area"), el("th", { class: "num" }, "Count"), el("th", { class: "num" }, "Share"),
      ])),
      el("tbody", {}, areas.map((a) => el("tr", {}, [
        el("td", { class: "data" }, a.area),
        el("td", { class: "num" }, String(a.count)),
        el("td", { class: "num dim" }, pct(a.share)),
      ]))),
    ]));
  }
  slot.appendChild(fa);
}

// ---- 3. frequency explorer (filtered slice) ----

function explorerCard(targets, datasets) {
  const card = el("div", { class: "card card-explorer" });
  card.appendChild(el("div", { class: "card-head" }, [
    el("h3", {}, "Frequency explorer"),
    el("span", { class: "kicker kicker-explorer" }, "descriptive count · filtered slice"),
  ]));
  card.appendChild(el("p", { class: "hint" },
    "Counts the most frequent value inside the current filter. This is a plain tally, " +
    "not a detection verdict — no confidence rating applies."));

  if (targets.length === 0) {
    card.appendChild(el("div", { class: "empty" }, "No targets yet. Add one from a dataset's Targets screen."));
    return card;
  }

  const target = el("select", { id: "fx-target" },
    [el("option", { value: "" }, "— select a target —")]
      .concat(targets.map((t) => targetOption(t, datasets))));
  const rankBy = el("select", { id: "fx-rank" }, [
    el("option", { value: "area" }, "Location / tower"),
    el("option", { value: "other_party" }, "Call partner"),
    el("option", { value: "call_type" }, "Call type"),
  ]);
  const callType = el("select", { id: "fx-type" },
    [el("option", { value: "" }, "Any")]
      .concat(CALL_TYPE_OPTIONS.map(([code, label]) => el("option", { value: String(code) }, label))));
  const area = el("input", { type: "text", id: "fx-area", placeholder: "exact area, e.g. Hamra" });
  const dateFrom = el("input", { type: "date", id: "fx-from" });
  const dateTo = el("input", { type: "date", id: "fx-to" });
  const hourFrom = el("input", { type: "number", id: "fx-hfrom", min: "0", max: "23", placeholder: "0" });
  const hourTo = el("input", { type: "number", id: "fx-hto", min: "0", max: "23", placeholder: "23" });

  const field = (labelText, forId, input) =>
    el("div", {}, [el("label", { for: forId }, labelText), input]);

  card.appendChild(el("div", { class: "filter-grid" }, [
    field("Target", "fx-target", target),
    field("Rank by", "fx-rank", rankBy),
    field("Call type", "fx-type", callType),
    field("Location", "fx-area", area),
    field("From date", "fx-from", dateFrom),
    field("To date", "fx-to", dateTo),
    field("From hour (0–23)", "fx-hfrom", hourFrom),
    field("To hour (0–23)", "fx-hto", hourTo),
  ]));

  const btn = el("button", { class: "btn btn-primary" }, "Count");
  const slot = el("div");
  card.appendChild(el("div", { class: "form-actions" }, [
    btn,
    el("span", { class: "hint" }, "Hours may wrap midnight (e.g. 22 → 6)."),
  ]));
  card.appendChild(slot);

  btn.addEventListener("click", async () => {
    clear(slot);
    if (!target.value) { slot.appendChild(msg("Select a target.")); return; }
    const params = { rank_by: rankBy.value };
    if (callType.value) params.call_type = callType.value;
    if (area.value.trim()) params.area = area.value.trim();
    if (dateFrom.value) params.date_from = dateFrom.value;
    if (dateTo.value) params.date_to = dateTo.value;
    if (hourFrom.value !== "") params.hour_from = hourFrom.value;
    if (hourTo.value !== "") params.hour_to = hourTo.value;

    btn.disabled = true;
    slot.appendChild(loading("Counting…"));
    try {
      const res = await api.frequency(Number(target.value), params);
      clear(slot);
      renderTally(slot, res);
    } catch (e) {
      clear(slot);
      slot.appendChild(msg(e.message));
    } finally {
      btn.disabled = false;
    }
  });

  return card;
}

function renderTally(slot, res) {
  if (res.total_records === 0 || res.top.length === 0) {
    slot.appendChild(el("div", { class: "empty" }, "No records match the current filter."));
    return;
  }
  const display = (v) => (res.rank_by === "call_type" ? callTypeLabel(v) : String(v));
  const winner = res.top[0];
  slot.appendChild(el("p", { class: "hint" },
    `${res.total_records} record(s) in the current filter. Most frequent:`));
  slot.appendChild(el("div", { class: "result-area mono" },
    `${display(winner.value)} — ${winner.count}×`));
  slot.appendChild(el("table", {}, [
    el("thead", {}, el("tr", {}, [
      el("th", {}, "Value"), el("th", { class: "num" }, "Count"),
    ])),
    el("tbody", {}, res.top.map((r) => el("tr", {}, [
      el("td", { class: "data" }, display(r.value)),
      el("td", { class: "num" }, String(r.count)),
    ]))),
  ]));
}

function pct(share) {
  const n = Number(share);
  if (!Number.isFinite(n)) return "—";
  return (n * 100).toFixed(1) + "%";
}
