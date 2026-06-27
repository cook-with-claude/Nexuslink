// DASHBOARD. API-MISMATCH #2: no stats endpoint — derive totals + recent imports
// client-side from /api/datasets + /api/targets (parallel fetch).

import { api } from "../api.js";
import { store } from "../store.js";
import { shell } from "../layout.js";
import { el, loading, clear, fmtDate } from "../components.js";

export async function dashboardScreen(app) {
  const page = shell(app);
  page.appendChild(el("h1", {}, "Dashboard"));
  const body = el("div");
  body.appendChild(loading());
  page.appendChild(body);

  const [datasets, targets] = await Promise.all([api.datasets(), api.targets()]);
  clear(body);

  const totalRecords = datasets.reduce((s, d) => s + (d.row_count || 0), 0);
  const stats = el("div", { class: "card" }, [
    el("div", { class: "grid-stats" }, [
      stat(datasets.length, "Datasets"),
      stat(targets.length, "Targets"),
      stat(totalRecords, "Records imported"),
    ]),
  ]);
  body.appendChild(stats);

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
    const rows = recent.map((d) =>
      el("tr", { class: "clickable", onclick: () => {
        store.activeDataset = { id: d.id, name: d.name };
        location.hash = `#/datasets/${d.id}/targets`;
      } }, [
        el("td", { class: "data" }, d.name),
        el("td", { class: "data dim" }, d.filename),
        el("td", { class: "num" }, String(d.row_count)),
        el("td", { class: "data dim" }, fmtDate(d.imported_at)),
      ]),
    );
    card.appendChild(el("table", {}, [
      el("thead", {}, el("tr", {}, [
        el("th", {}, "Name"), el("th", {}, "File"),
        el("th", { class: "num" }, "Rows"), el("th", {}, "Imported"),
      ])),
      el("tbody", {}, rows),
    ]));
  }
  body.appendChild(card);

  body.appendChild(el("div", { class: "form-actions" }, [
    el("a", { href: "#/datasets", class: "btn" }, "View datasets"),
    el("a", { href: "#/import", class: "btn btn-primary" }, "Import dataset"),
  ]));
}

function stat(num, lbl) {
  return el("div", { class: "stat" }, [
    el("div", { class: "num" }, String(num)),
    el("div", { class: "lbl" }, lbl),
  ]);
}
