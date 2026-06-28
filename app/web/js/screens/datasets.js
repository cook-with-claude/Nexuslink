// DATASETS. Table of all datasets. Row -> set active dataset -> its targets.
// Import new -> #/import. Delete -> inline confirm -> DELETE /api/datasets/<id>.

import { api } from "../api.js";
import { store } from "../store.js";
import { shell } from "../layout.js";
import { el, loading, clear, fmtDate, confirmInline, toast, navigableRows, icon } from "../components.js";
import { setStatusCounts } from "../statusbar.js";

export async function datasetsScreen(app) {
  const { page, setCrumb, setActions } = shell(app);
  setCrumb("Datasets");
  setActions([el("a", { href: "#/import", class: "btn btn-primary" }, [icon("upload"), "Import new"])]);

  const body = el("div");
  body.appendChild(loading());
  page.appendChild(body);

  const [datasets, targets] = await Promise.all([api.datasets(), api.targets()]);
  setStatusCounts(datasets.length, targets.length);
  clear(body);

  if (datasets.length === 0) {
    body.appendChild(el("div", { class: "card" }, el("div", { class: "empty" }, [
      "No datasets imported. ",
      el("a", { href: "#/import", class: "link" }, "Import your first dataset"),
      ".",
    ])));
    return;
  }

  const tbody = el("tbody");
  for (const d of datasets) {
    const open = () => {
      store.activeDataset = { id: d.id, name: d.name };
      location.hash = `#/datasets/${d.id}/targets`;
    };
    const delBtn = el("button", { class: "btn btn-sm btn-danger", onclick: (e) => {
      e.stopPropagation();
      confirmInline(delBtn, async () => {
        try {
          await api.deleteDataset(d.id);
          toast("Dataset deleted");
          datasetsScreen(app);
        } catch (err) { toast(err.message, "error"); }
      }, "Delete dataset?");
    } }, "Delete");

    const actions = el("td", { class: "right", onclick: (e) => e.stopPropagation() }, [delBtn]);

    tbody.appendChild(el("tr", { class: "clickable", onclick: open }, [
      el("td", { class: "data" }, d.name),
      el("td", { class: "data dim" }, d.filename),
      el("td", { class: "num" }, Number(d.row_count).toLocaleString()),
      el("td", { class: "num dim" }, String(d.skipped_count)),
      el("td", { class: "data dim" }, fmtDate(d.imported_at)),
      actions,
    ]));
  }
  navigableRows(tbody);

  body.appendChild(el("div", { class: "card" }, el("table", {}, [
    el("thead", {}, el("tr", {}, [
      el("th", {}, "Name"), el("th", {}, "File"),
      el("th", { class: "num" }, "Rows"), el("th", { class: "num" }, "Skipped"),
      el("th", {}, "Imported"), el("th", { class: "right" }, ""),
    ])),
    tbody,
  ])));
}
