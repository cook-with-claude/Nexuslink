// EXPORT. App-wide: linked from the rail, so it is one click away on every
// screen. Exports the STORED detection answers (latest analysis_results row per
// target) — it never recomputes, so the file always matches what the app shows.

import { api, downloadResultsXlsx } from "../api.js";
import { shell } from "../layout.js";
import { el, loading, clear, msg, toast, icon } from "../components.js";

export async function exportScreen(app) {
  const { page, setCrumb } = shell(app);
  setCrumb(["Export"]);
  const body = el("div");
  body.appendChild(loading());
  page.appendChild(body);

  const targets = await api.targets();
  clear(body);

  const card = el("div", { class: "card" });
  card.appendChild(el("h3", {}, "Export detection results"));
  card.appendChild(el("p", { class: "hint" },
    "Writes the stored detection answers — home, work, frequent areas, and their " +
    "confidence ratings — to an .xlsx file. Targets not analyzed yet appear as " +
    "“not analyzed”."));

  if (targets.length === 0) {
    card.appendChild(el("div", { class: "empty" }, "No targets to export yet."));
    body.appendChild(card);
    return;
  }

  const scope = el("select", { id: "ex-scope" },
    [el("option", { value: "" }, `All targets (${targets.length})`)]
      .concat(targets.map((t) =>
        el("option", { value: String(t.id) }, `${t.name} — ${t.phone_number}`))));

  const nameInput = el("input", {
    type: "text", id: "ex-name", value: "lapassion_results", spellcheck: "false",
  });

  // Filesystem-illegal characters stripped; ".xlsx" is always appended (typing
  // it yourself is fine — it won't double up). Blank falls back to the default.
  const chosenFilename = () => {
    const clean = nameInput.value
      .replace(/[\\/:*?"<>|]/g, "").trim().replace(/\.xlsx$/i, "").trim();
    return (clean || "lapassion_results") + ".xlsx";
  };

  const btn = el("button", { class: "btn btn-primary" }, [icon("download"), "Download .xlsx"]);
  const errSlot = el("div");
  btn.addEventListener("click", async () => {
    clear(errSlot);
    btn.disabled = true;
    try {
      await downloadResultsXlsx(scope.value || null, chosenFilename());
      toast("Export downloaded");
    } catch (e) {
      errSlot.appendChild(msg(e.message));
    } finally {
      btn.disabled = false;
    }
  });

  card.appendChild(el("label", { for: "ex-scope" }, "Scope"));
  card.appendChild(scope);
  card.appendChild(el("label", { for: "ex-name" }, "File name (.xlsx added automatically)"));
  card.appendChild(nameInput);
  card.appendChild(errSlot);
  card.appendChild(el("div", { class: "form-actions" }, [btn]));
  body.appendChild(card);
}
