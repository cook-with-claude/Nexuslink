// IMPORT. FormData POST to /api/imports with a loading state so the UI never
// looks frozen. API-MISMATCH #11: do NOT set Content-Type (browser sets the
// multipart boundary) — handled in api.js by passing `form`.

import { api, ApiError } from "../api.js";
import { store } from "../store.js";
import { shell } from "../layout.js";
import { el, clear, msg } from "../components.js";

export async function importScreen(app) {
  const page = shell(app);
  page.appendChild(el("h1", {}, "Import dataset"));
  page.appendChild(el("p", { class: "subhead" }, "Upload a .xlsx CDR export. Rows that fail validation are skipped and reported below."));

  const card = el("div", { class: "card" });
  page.appendChild(card);
  const resultSlot = el("div");
  page.appendChild(resultSlot);

  const name = el("input", { type: "text", id: "name", placeholder: "e.g. Operator A — March" });
  const file = el("input", { type: "file", id: "file", accept: ".xlsx" });
  const errSlot = el("div");
  const btn = el("button", { class: "btn btn-primary", type: "submit" }, "Import");

  const form = el("form", {}, [
    el("label", { for: "name" }, "Dataset name"), name,
    el("label", { for: "file" }, "File (.xlsx)"), file,
    errSlot,
    el("div", { class: "form-actions" }, [btn]),
  ]);
  card.appendChild(form);

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    clear(errSlot);
    clear(resultSlot);
    if (!name.value.trim()) { errSlot.appendChild(msg("A dataset name is required.")); return; }
    if (!file.files || file.files.length === 0) { errSlot.appendChild(msg("Choose a .xlsx file.")); return; }

    const fd = new FormData();
    fd.append("name", name.value.trim());
    fd.append("file", file.files[0]);

    btn.disabled = true;
    const prevLabel = btn.textContent;
    clear(btn);
    btn.appendChild(el("span", { class: "spinner" }));
    btn.appendChild(document.createTextNode(" Importing…"));

    try {
      const data = await api.importDataset(fd);
      resultSlot.appendChild(renderSummary(data, name.value.trim()));
      form.reset();
    } catch (err) {
      const text = err instanceof ApiError
        ? (err.status === 413 ? "File is too large (limit 50 MiB)." : err.message)
        : "Import failed — please retry.";
      errSlot.appendChild(msg(text));
    } finally {
      btn.disabled = false;
      clear(btn);
      btn.textContent = prevLabel;
    }
  });

  name.focus();
}

function renderSummary(data, dsName) {
  const card = el("div", { class: "card" });
  card.appendChild(el("h3", {}, "Import complete"));
  card.appendChild(el("div", { class: "grid-stats" }, [
    statline(data.imported, "Imported"),
    statline(data.skipped, "Skipped"),
  ]));

  if (data.skipped_reasons && data.skipped_reasons.length) {
    card.appendChild(el("h3", {}, "Skipped rows"));
    const rows = data.skipped_reasons.map((r) =>
      el("tr", {}, [el("td", { class: "num" }, String(r.row)), el("td", { class: "data dim" }, r.reason)]));
    card.appendChild(el("table", {}, [
      el("thead", {}, el("tr", {}, [el("th", { class: "num" }, "Row"), el("th", {}, "Reason")])),
      el("tbody", {}, rows),
    ]));
  }

  card.appendChild(el("div", { class: "form-actions" }, [
    el("button", { class: "btn btn-primary", onclick: () => {
      store.activeDataset = { id: data.dataset_id, name: dsName };
      location.hash = `#/datasets/${data.dataset_id}/targets`;
    } }, "View targets"),
    el("a", { href: "#/datasets", class: "btn" }, "All datasets"),
  ]));
  return card;
}

function statline(num, lbl) {
  return el("div", { class: "stat" }, [
    el("div", { class: "num" }, String(num)),
    el("div", { class: "lbl" }, lbl),
  ]);
}
