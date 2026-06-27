// RESULTS. Loads from store.lastResult (set by analyze) or GET /result on reload.
// API-MISMATCH #6: analyze payload omits the dataset name — join client-side via
// target -> dataset_id (/api/targets) -> dataset name (/api/datasets).
// API-MISMATCH #8: frequent_contacts + frequent_areas_confidence are rendered.
// API-MISMATCH #9: near_tie tag + alternatives are surfaced (display only).

import { api } from "../api.js";
import { store } from "../store.js";
import { shell } from "../layout.js";
import { el, loading, clear, confidencePill, gateTrace, fmtDate } from "../components.js";

export async function resultsScreen(app, params) {
  const targetId = Number(params.id);
  const page = shell(app);
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
  page.insertBefore(el("div", { class: "result-head" }, [
    el("div", {}, [
      el("h1", {}, payload.target.name),
      el("p", { class: "subhead" }, [
        el("span", { class: "mono" }, payload.target.phone_number),
        datasetName ? " · " : "",
        datasetName ? el("span", { class: "mono" }, datasetName) : "",
        " · analyzed ", fmtDate(payload.analyzed_at),
      ]),
    ]),
    dsBackId ? el("a", { href: `#/datasets/${dsBackId}/targets`, class: "btn" }, "← Targets") : el("a", { href: "#/datasets", class: "btn" }, "← Datasets"),
  ]), body);

  // Home / Work side by side
  body.appendChild(el("div", { class: "result-grid" }, [
    detectionCard("Home", payload.home),
    detectionCard("Work", payload.work),
  ]));

  // Frequent areas + overall area confidence
  body.appendChild(frequentAreasCard(payload.frequent_areas, payload.frequent_areas_confidence));

  // Frequent contacts
  body.appendChild(frequentContactsCard(payload.frequent_contacts));
}

function detectionCard(title, r) {
  const card = el("div", { class: "card" });
  card.appendChild(el("div", { class: "result-head" }, [
    el("h3", {}, title),
    confidencePill(r),
  ]));
  const area = (r && r.area) ? r.area : "—";
  card.appendChild(el("div", { class: "result-area mono" }, area));

  if (r && r.alternatives && r.alternatives.length) {
    card.appendChild(el("div", { class: "alts" }, [
      "alternatives: ",
      ...r.alternatives.flatMap((a, i) => [i ? ", " : "", el("span", { class: "mono" }, a)]),
    ]));
  }
  card.appendChild(gateTrace(r));
  return card;
}

function frequentAreasCard(areas, conf) {
  const card = el("div", { class: "card" });
  card.appendChild(el("div", { class: "result-head" }, [
    el("h3", {}, "Frequent areas"),
    confidencePill(conf),
  ]));
  if (!areas || areas.length === 0) {
    card.appendChild(el("div", { class: "empty" }, "No area activity."));
  } else {
    const rows = areas.map((a) => el("tr", {}, [
      el("td", { class: "data" }, a.area),
      el("td", { class: "num" }, String(a.count)),
      el("td", { class: "num dim" }, pct(a.share)),
    ]));
    card.appendChild(el("table", {}, [
      el("thead", {}, el("tr", {}, [
        el("th", {}, "Area"), el("th", { class: "num" }, "Count"), el("th", { class: "num" }, "Share"),
      ])),
      el("tbody", {}, rows),
    ]));
  }
  if (conf) card.appendChild(gateTrace(conf, "Overall area gate trace"));
  return card;
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

function pct(share) {
  const n = Number(share);
  if (!Number.isFinite(n)) return "—";
  return (n * 100).toFixed(1) + "%";
}
