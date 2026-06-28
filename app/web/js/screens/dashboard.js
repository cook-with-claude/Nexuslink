// DASHBOARD. API-MISMATCH #2: no stats endpoint — derive totals + recent imports
// client-side from /api/datasets + /api/targets (parallel fetch). Counts are also
// pushed to the status bar.

import { api } from "../api.js";
import { store } from "../store.js";
import { shell } from "../layout.js";
import { el, loading, clear, fmtDate, navigableRows, icon } from "../components.js";
import { setStatusCounts } from "../statusbar.js";

export async function dashboardScreen(app) {
  const { page, setCrumb, setActions } = shell(app);
  setCrumb("Dashboard");
  setActions([el("a", { href: "#/import", class: "btn btn-primary" }, [icon("upload"), "Import dataset"])]);

  const body = el("div");
  body.appendChild(loading());
  page.appendChild(body);

  const [datasets, targets] = await Promise.all([api.datasets(), api.targets()]);
  setStatusCounts(datasets.length, targets.length);
  clear(body);

  const totalRecords = datasets.reduce((s, d) => s + (d.row_count || 0), 0);
  body.appendChild(el("div", { class: "card" }, [
    el("div", { class: "grid-stats" }, [
      stat(datasets.length, "Datasets"),
      stat(targets.length, "Targets"),
      stat(totalRecords.toLocaleString(), "Records imported"),
    ]),
  ]));

  // recent imports = datasets sorted by imported_at desc, top 5
  const recent = [...datasets].sort((a, b) => (b.imported_at || "").localeCompare(a.imported_at || "")).slice(0, 5);
  const card = el("div", { class: "card" });
  card.appendChild(el("h3", {}, "Recent imports"));
  if (recent.length === 0) {
    card.appendChild(el("div", { class: "empty" }, [
      "No datasets yet. ",
      el("a", { href: "#/import", class: "link" }, "Import one"),
      ".",
    ]));
  } else {
    const tbody = el("tbody", {}, recent.map((d) =>
      el("tr", { class: "clickable", onclick: () => {
        store.activeDataset = { id: d.id, name: d.name };
        location.hash = `#/datasets/${d.id}/targets`;
      } }, [
        el("td", { class: "data" }, d.name),
        el("td", { class: "data dim" }, d.filename),
        el("td", { class: "num" }, Number(d.row_count).toLocaleString()),
        el("td", { class: "data dim" }, fmtDate(d.imported_at)),
      ]),
    ));
    navigableRows(tbody);
    card.appendChild(el("table", {}, [
      el("thead", {}, el("tr", {}, [
        el("th", {}, "Name"), el("th", {}, "File"),
        el("th", { class: "num" }, "Rows"), el("th", {}, "Imported"),
      ])),
      tbody,
    ]));
  }
  body.appendChild(card);
}

function stat(num, lbl) {
  return el("div", { class: "stat" }, [
    el("div", { class: "num" }, String(num)),
    el("div", { class: "lbl" }, lbl),
  ]);
}
