// SPREADSHEET. Three deliberately separated parts, because they answer
// different questions:
//   1. Records — read-only view of the imported rows, filterable per column
//      from the header row (like a sheet's autofilter); filters are applied
//      server-side so paging and totals stay correct. Clicking a phone number
//      runs detection for that user (creating the target if needed).
//   2. Detection — the confidence-gated INFERENCE. Always runs on the target's
//      FULL record set: the gates depend on sample size (N), so applying the
//      sheet's filters here would shrink N and produce wrong ratings.
//   3. Frequency explorer — a plain descriptive tally over the FILTERED slice.
//      No home/work labels and no confidence, by design: a count is not a
//      verdict, and filtering is legitimate here precisely because it's a tally.

import { api } from "../api.js";
import { shell } from "../layout.js";
import {
  el, loading, clear, msg, toast, confidencePill, gateTrace, sampleNote,
} from "../components.js";
import { callTypeDisplay, CALL_TYPE_OPTIONS } from "../call-types.js";

const PAGE_SIZE = 100;

export async function spreadsheetScreen(app) {
  const { page, setCrumb } = shell(app);
  setCrumb(["Spreadsheet"]);
  const body = el("div");
  body.appendChild(loading());
  page.appendChild(body);

  let [datasets, targets] = await Promise.all([api.datasets(), api.targets()]);
  clear(body);

  if (datasets.length === 0) {
    body.appendChild(el("div", { class: "card" },
      el("div", { class: "empty" }, "No datasets yet. Import a .xlsx first.")));
    return;
  }

  const detection = detectionCard(datasets);
  const explorer = explorerCard(datasets);
  detection.refresh(targets);
  explorer.refresh(targets);

  // Click a user in the sheet -> make sure a target exists for that phone in
  // that dataset (created on the fly, named after the number), then run the
  // full-set detection in the Detection card below.
  const onUserDetect = async (datasetId, phone) => {
    let t = targets.find((x) => x.dataset_id === datasetId && x.phone_number === phone);
    if (!t) {
      try {
        await api.createTarget(phone, datasetId, phone);
        toast(`Target created for ${phone}`);
      } catch (e) {
        // CONFLICT = someone created it since we cached the list; re-fetch wins.
        if (e.code !== "CONFLICT") { toast(e.message); return; }
      }
      targets = await api.targets();
      detection.refresh(targets);
      explorer.refresh(targets);
      t = targets.find((x) => x.dataset_id === datasetId && x.phone_number === phone);
      if (!t) return;
    }
    detection.card.scrollIntoView({ behavior: "smooth", block: "start" });
    detection.runFor(t.id);
  };

  body.appendChild(recordsCard(datasets, onUserDetect));
  body.appendChild(detection.card);
  body.appendChild(explorer.card);
}

function targetOption(t, datasets) {
  const d = datasets.find((x) => x.id === t.dataset_id);
  return el("option", { value: String(t.id) },
    `${t.name} — ${t.phone_number}${d ? ` (${d.name})` : ""}`);
}

function debounce(fn, ms) {
  let timer = null;
  return () => { clearTimeout(timer); timer = setTimeout(fn, ms); };
}

// ---- 1. records view ----

function recordsCard(datasets, onUserDetect) {
  const card = el("div", { class: "card" });
  card.appendChild(el("div", { class: "card-head" }, [
    el("h3", {}, "Records"),
    el("span", { class: "kicker" }, "read-only view"),
  ]));

  const picker = el("select", { id: "ss-dataset" },
    datasets.map((d) => el("option", { value: String(d.id) }, `${d.name} (${d.row_count} rows)`)));
  const unitPicker = el("select", { id: "ss-unit" }, [
    el("option", { value: "s" }, "seconds (s)"),
    el("option", { value: "min" }, "minutes (min)"),
  ]);
  const field = (labelText, forId, input) =>
    el("div", {}, [el("label", { for: forId }, labelText), input]);
  card.appendChild(el("div", { class: "filter-grid" }, [
    field("Dataset", "ss-dataset", picker),
    field("Duration unit", "ss-unit", unitPicker),
  ]));
  card.appendChild(el("p", { class: "hint" },
    "Filter columns in the header row. Click a phone number to run detection on that user."));

  // Column filters live IN the sheet's header row. Applied server-side; the
  // table skeleton is built once so typing in a filter never loses focus.
  const fPhone = el("select", { class: "col-filter", "aria-label": "filter phone" },
    [el("option", { value: "" }, "All")]);
  const fArea = el("input", {
    class: "col-filter", type: "text", placeholder: "contains…", "aria-label": "filter area",
  });
  const fType = el("select", { class: "col-filter", "aria-label": "filter type" },
    [el("option", { value: "" }, "Any")]
      .concat(CALL_TYPE_OPTIONS.map(([code, label]) => el("option", { value: String(code) }, label))));
  const fParty = el("input", {
    class: "col-filter", type: "text", placeholder: "contains…", "aria-label": "filter other party",
  });

  // Sortable headers: click toggles oldest/newest (Timestamp) or
  // shortest/longest (Duration). Server-side, so sorting spans all pages.
  let sortCol = null;
  let sortDir = "asc";
  const tsBtn = el("button", { class: "link", title: "Sort by time" }, "Timestamp");
  const durBtn = el("button", { class: "link", title: "Sort by duration" }, "Duration (s)");
  const sortMark = (col) => (sortCol !== col ? "" : (sortDir === "asc" ? " ↑" : " ↓"));
  const tbody = el("tbody");
  card.appendChild(el("div", { class: "table-scroll" }, el("table", {}, [
    el("thead", {}, [
      el("tr", {}, [
        el("th", {}, "Phone"), el("th", {}, "IMEI"), el("th", {}, "Area"),
        el("th", {}, tsBtn), el("th", {}, "Type"), el("th", { class: "num" }, durBtn),
        el("th", {}, "Other party"), el("th", {}, "Other IMEI"), el("th", {}, "Other area"),
      ]),
      el("tr", { class: "filter-row" }, [
        el("th", {}, fPhone), el("th", {}), el("th", {}, fArea),
        el("th", {}), el("th", {}, fType), el("th", {}),
        el("th", {}, fParty), el("th", {}), el("th", {}),
      ]),
    ]),
    tbody,
  ])));
  const pagerSlot = el("div");
  card.appendChild(pagerSlot);

  const filters = () => ({
    phone_number: fPhone.value,
    call_type: fType.value,
    area: fArea.value,
    other_party: fParty.value,
    sort: sortCol || "",
    dir: sortCol ? sortDir : "",
  });

  let userSeq = 0; // drop out-of-order phone-list responses from fast dataset switches
  const loadUsers = async () => {
    const mine = ++userSeq;
    let users = [];
    try {
      users = await api.phoneNumbers(Number(picker.value));
    } catch {
      // The records request below surfaces any real error; a user list that
      // failed to load just leaves the filter at "All".
    }
    if (mine !== userSeq) return; // a newer dataset selection superseded this list
    clear(fPhone);
    fPhone.appendChild(el("option", { value: "" }, "All"));
    users.forEach((u) => fPhone.appendChild(
      el("option", { value: u.phone_number }, `${u.phone_number} (${u.count})`)));
  };

  const fmtDuration = (secs) =>
    unitPicker.value === "min" ? (secs / 60).toFixed(1) : String(secs);
  const statusRow = (text) => el("tr", {}, el("td", { class: "dim", colspan: "9" }, text));

  let offset = 0;
  let seq = 0; // drop out-of-order responses from fast consecutive filter edits
  const load = async () => {
    const mine = ++seq;
    clear(tbody);
    tbody.appendChild(statusRow("Loading records…"));
    clear(pagerSlot);
    let res;
    try {
      res = await api.records(Number(picker.value), offset, PAGE_SIZE, filters());
    } catch (e) {
      if (mine !== seq) return;
      clear(tbody);
      tbody.appendChild(statusRow(e.message));
      return;
    }
    if (mine !== seq) return;
    clear(tbody);
    tsBtn.textContent = "Timestamp" + sortMark("timestamp");
    durBtn.textContent =
      (unitPicker.value === "min" ? "Duration (min)" : "Duration (s)") + sortMark("duration_seconds");
    if (res.total === 0) {
      tbody.appendChild(statusRow("No records match the current filters."));
      return;
    }

    res.rows.forEach((r) => {
      const userBtn = el("button", {
        class: "link data", title: "Run detection for this user",
      }, r.phone_number);
      userBtn.addEventListener("click", () => onUserDetect(Number(picker.value), r.phone_number));
      tbody.appendChild(el("tr", {}, [
        el("td", { class: "data" }, userBtn),
        el("td", { class: "data dim" }, r.imei || "—"),
        el("td", { class: "data" }, r.area),
        el("td", { class: "data dim" }, r.timestamp),
        el("td", {}, callTypeDisplay(r.call_type)),
        el("td", { class: "num" }, fmtDuration(r.duration_seconds)),
        el("td", { class: "data" }, r.other_party || "—"),
        el("td", { class: "data dim" }, r.other_imei || "—"),
        el("td", { class: "data dim" }, r.other_area || "—"),
      ]));
    });

    const from = res.offset + 1;
    const to = res.offset + res.rows.length;
    const prev = el("button", { class: "btn btn-sm", disabled: res.offset === 0 ? "disabled" : null }, "‹ Prev");
    const next = el("button", { class: "btn btn-sm", disabled: to >= res.total ? "disabled" : null }, "Next ›");
    prev.addEventListener("click", () => { offset = Math.max(0, offset - PAGE_SIZE); load(); });
    next.addEventListener("click", () => { offset += PAGE_SIZE; load(); });
    pagerSlot.appendChild(el("div", { class: "pager" }, [
      prev, next, el("span", { class: "dim" }, `${from}–${to} of ${res.total} records`),
    ]));
  };

  const refilter = () => { offset = 0; load(); };
  const sortBy = (col) => {
    if (sortCol === col) sortDir = sortDir === "asc" ? "desc" : "asc";
    else { sortCol = col; sortDir = "asc"; }
    refilter();
  };
  tsBtn.addEventListener("click", () => sortBy("timestamp"));
  durBtn.addEventListener("click", () => sortBy("duration_seconds"));
  picker.addEventListener("change", async () => { offset = 0; await loadUsers(); load(); });
  unitPicker.addEventListener("change", () => load());
  fPhone.addEventListener("change", refilter);
  fType.addEventListener("change", refilter);
  const typed = debounce(refilter, 300);
  fArea.addEventListener("input", typed);
  fParty.addEventListener("input", typed);

  loadUsers().then(load);
  return card;
}

// ---- 2. detection (full record set) ----

function detectionCard(datasets) {
  const card = el("div", { class: "card card-inference" });
  card.appendChild(el("div", { class: "card-head" }, [
    el("h3", {}, "Detection"),
    el("span", { class: "kicker kicker-inference" }, "inference · full record set"),
  ]));
  card.appendChild(el("p", { class: "hint" },
    "Runs the confidence-gated detection on the target's complete record set. " +
    "The sheet and explorer filters never apply here: the gates depend on sample size, " +
    "and a filtered subset would produce wrong ratings."));

  const inner = el("div");
  card.appendChild(inner);

  let picker = null;
  let btn = null;
  let slot = null;
  let seq = 0; // drop stale detections when a newer run starts (e.g. runFor from a fast second phone-click)

  const run = async (targetId) => {
    const mine = ++seq;
    clear(slot);
    btn.disabled = true;
    slot.appendChild(loading("Analyzing…"));
    try {
      const payload = await api.analyze(targetId);
      if (mine !== seq) return; // a newer run superseded this one — don't render a stale verdict
      clear(slot);
      renderDetection(slot, payload);
    } catch (e) {
      if (mine !== seq) return;
      clear(slot);
      slot.appendChild(msg(e.message));
    } finally {
      if (mine === seq) btn.disabled = false;
    }
  };

  // Rebuilds the picker whenever the target list changes (e.g. a target was
  // created by clicking a user in the sheet); keeps the current selection.
  const refresh = (targets) => {
    const keep = picker ? picker.value : "";
    clear(inner);
    if (targets.length === 0) {
      picker = null; btn = null; slot = null;
      inner.appendChild(el("div", { class: "empty" },
        "No targets yet. Add one from a dataset's Targets screen, or click a phone number in the sheet above."));
      return;
    }
    picker = el("select", { id: "ss-det-target" },
      [el("option", { value: "" }, "— select a target —")]
        .concat(targets.map((t) => targetOption(t, datasets))));
    if (keep) picker.value = keep;
    btn = el("button", { class: "btn btn-primary" }, "Run detection");
    slot = el("div");
    btn.addEventListener("click", () => {
      if (!picker.value) { clear(slot); slot.appendChild(msg("Select a target.")); return; }
      run(Number(picker.value));
    });
    inner.appendChild(el("label", { for: "ss-det-target" }, "Target"));
    inner.appendChild(picker);
    inner.appendChild(el("div", { class: "form-actions" }, [btn]));
    inner.appendChild(slot);
  };

  const runFor = (targetId) => {
    if (!picker) return;
    picker.value = String(targetId);
    run(targetId);
  };

  return { card, refresh, runFor };
}

// Same visual language as the RESULTS screen: confidencePill + gateTrace from
// components.js keep the "one visual language / no raw JSON" rules. Frequent
// areas deliberately carry NO confidence pill — a frequency table is a count,
// not a gated verdict.
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
    el("span", { class: "kicker" }, "count, not a verdict"),
  ]));
  const areas = payload.frequent_areas || [];
  if (areas.length === 0) {
    fa.appendChild(el("div", { class: "empty" }, "No area activity."));
  } else {
    const note = sampleNote(areas, payload.frequent_areas_confidence);
    if (note) fa.appendChild(note);
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

function explorerCard(datasets) {
  const card = el("div", { class: "card card-explorer" });
  card.appendChild(el("div", { class: "card-head" }, [
    el("h3", {}, "Frequency explorer"),
    el("span", { class: "kicker kicker-explorer" }, "descriptive count · filtered slice"),
  ]));
  card.appendChild(el("p", { class: "hint" },
    "Counts the most frequent value inside the current filter. This is a plain tally, " +
    "not a detection verdict — no confidence rating applies."));

  const inner = el("div");
  card.appendChild(inner);

  const FIELD_IDS = ["fx-target", "fx-rank", "fx-type", "fx-area",
                     "fx-from", "fx-to", "fx-hfrom", "fx-hto"];

  const refresh = (targets) => {
    // Preserve any in-progress filter values across a rebuild — refresh() fires
    // when a target is created by clicking a phone in the grid, and that click
    // was aimed at the Detection card, not at wiping the explorer the user set up.
    const keep = {};
    for (const id of FIELD_IDS) {
      const prev = inner.querySelector("#" + id);
      if (prev) keep[id] = prev.value;
    }
    clear(inner);
    if (targets.length === 0) {
      inner.appendChild(el("div", { class: "empty" },
        "No targets yet. Add one from a dataset's Targets screen, or click a phone number in the sheet above."));
      return;
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

    // Restore preserved values. Setting a <select> to an absent option is a
    // no-op, so a target that no longer exists just falls back to the prompt.
    for (const [elmt, id] of [[target, "fx-target"], [rankBy, "fx-rank"],
        [callType, "fx-type"], [area, "fx-area"], [dateFrom, "fx-from"],
        [dateTo, "fx-to"], [hourFrom, "fx-hfrom"], [hourTo, "fx-hto"]]) {
      if (id in keep) elmt.value = keep[id];
    }

    inner.appendChild(el("div", { class: "filter-grid" }, [
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
    inner.appendChild(el("div", { class: "form-actions" }, [
      btn,
      el("span", { class: "hint" }, "Hours may wrap midnight (e.g. 22 → 6)."),
    ]));
    inner.appendChild(slot);

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
  };

  return { card, refresh };
}

function renderTally(slot, res) {
  if (res.total_records === 0) {
    slot.appendChild(el("div", { class: "empty" }, "No records match the current filter."));
    return;
  }
  if (res.top.length === 0) {
    // Records matched, but every one is NULL for the ranked column (e.g.
    // ranking by call partner over location-only rows). Saying "no records
    // match" here would be a lie — the filter matched total_records of them.
    slot.appendChild(el("div", { class: "empty" },
      `${res.total_records} record(s) match, but none carry a value for this ranking.`));
    return;
  }
  const display = (v) => (res.rank_by === "call_type" ? callTypeDisplay(v) : String(v));
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
