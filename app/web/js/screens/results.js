// RESULTS. Loads from store.lastResult (set by analyze) or GET /result on reload.
// API-MISMATCH #6: analyze payload omits the dataset name — join client-side via
// target -> dataset_id (/api/targets) -> dataset name (/api/datasets).
// API-MISMATCH #8: frequent areas/contacts are plain counts, not gated verdicts,
// so they carry NO confidence pill (a pill would misread as a rating on the tally).
// frequent_areas_confidence is used only for its record count (total_window_records)
// to show a descriptive sample-size note — the one gate that transfers to a tally.
// API-MISMATCH #9: near_tie tag + alternatives are surfaced (display only).

import { api } from "../api.js";
import { store } from "../store.js";
import { shell } from "../layout.js";
import { el, loading, clear, detectionBlock, frequentAreasBlock, fmtDate, icon } from "../components.js";
import { setActiveDatasetLabel } from "../statusbar.js";

export async function resultsScreen(app, params) {
  const targetId = Number(params.id);
  const { page, setCrumb, setActions } = shell(app);
  const body = el("div");
  body.appendChild(loading("Loading analysis…"));
  page.appendChild(body);

  // Prefer the cached analyze payload, else fetch the stored latest result.
  let payload = store.lastResult && store.lastResult.target && store.lastResult.target.id === targetId
    ? store.lastResult : null;
  if (!payload) payload = await api.result(targetId);

  // Join dataset name (gap #6): target -> dataset_id -> dataset name. The two
  // lookups are independent, so fetch them in parallel.
  let datasetName = store.activeDataset ? store.activeDataset.name : null;
  try {
    const [targets, datasets] = await Promise.all([api.targets(), api.datasets()]);
    const t = targets.find((x) => x.id === targetId);
    const d = t && datasets.find((x) => x.id === t.dataset_id);
    if (d) { datasetName = d.name; store.activeDataset = { id: d.id, name: d.name }; }
  } catch { /* name is best-effort; results still render without it */ }

  clear(body);

  const dsBackId = store.activeDataset ? store.activeDataset.id : null;
  setActiveDatasetLabel(datasetName);
  setCrumb([
    { text: "Datasets", href: "#/datasets" },
    datasetName
      ? { text: datasetName,
          href: dsBackId ? `#/datasets/${dsBackId}/targets` : undefined }
      : null,
    { text: payload.target.name, sub: payload.target.phone_number },
  ]);
  setActions([
    dsBackId
      ? el("a", { href: `#/datasets/${dsBackId}/targets`, class: "btn" }, [icon("back"), "Targets"])
      : el("a", { href: "#/datasets", class: "btn" }, [icon("back"), "Datasets"]),
  ]);

  body.appendChild(el("p", { class: "hint" }, `Analyzed ${fmtDate(payload.analyzed_at)}.`));

  // Home / Work side by side
  body.appendChild(el("div", { class: "result-grid" }, [
    detectionBlock("Home", payload.home),
    detectionBlock("Work", payload.work),
  ]));

  // Frequent areas (a count — no confidence by design, but show the sample size)
  body.appendChild(frequentAreasBlock(payload.frequent_areas, payload.frequent_areas_confidence));

  // Frequent contacts
  body.appendChild(frequentContactsCard(payload.frequent_contacts));
}

function frequentContactsCard(contacts) {
  const card = el("div", { class: "card" });
  card.appendChild(el("h3", {}, "Frequent contacts"));
  if (!contacts || contacts.length === 0) {
    card.appendChild(el("div", { class: "empty" }, "No contacts."));
    return card;
  }
  const rows = contacts.map((c) => el("tr", {}, [
    el("td", { class: "data" }, c.number),
    el("td", { class: "num" }, String(c.total)),
    el("td", { class: "num dim" }, `${c.call_out}/${c.call_in}`),
    el("td", { class: "num dim" }, `${c.sms_out}/${c.sms_in}`),
  ]));
  card.appendChild(el("table", {}, [
    el("thead", {}, el("tr", {}, [
      el("th", {}, "Number"), el("th", { class: "num" }, "Total"),
      el("th", { class: "num" }, "Calls out/in"), el("th", { class: "num" }, "SMS out/in"),
    ])),
    el("tbody", {}, rows),
  ]));
  return card;
}
