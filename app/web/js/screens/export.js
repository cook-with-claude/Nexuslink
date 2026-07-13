// EXPORT. App-wide: linked from the rail, so it is one click away on every
// screen. Exports the STORED detection answers (latest analysis_results row per
// target) — it never recomputes, so the file always matches what the app shows.

import { api, downloadResultsXlsx } from "../api.js";
import { shell } from "../layout.js";
import { el, loading, clear, msg, toast, icon, confirmInline, fmtDate } from "../components.js";

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
    type: "text", id: "ex-name", value: "nexuslink_results", spellcheck: "false",
  });

  // Filesystem-illegal characters stripped; ".xlsx" is always appended (typing
  // it yourself is fine — even a repeated ".xlsx.xlsx" won't double up). Blank
  // falls back to the default.
  const chosenFilename = () => {
    const clean = nameInput.value
      .replace(/[\\/:*?"<>|]/g, "").trim().replace(/(\.xlsx)+$/i, "").trim();
    return (clean || "nexuslink_results") + ".xlsx";
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

  body.appendChild(await savedItemsCard());
}

// Curation list for the click-to-save export staging: everything saved from the
// Spreadsheet tab (pair matches + explorer counts) with a remove button each, so
// a mis-saved item doesn't haunt every future export. The workbook's "Contact
// matches" / "Frequency counts" sheets carry exactly what is listed here.
async function savedItemsCard() {
  const card = el("div", { class: "card" });
  card.appendChild(el("div", { class: "card-head" }, [
    el("h3", {}, "Saved for export"),
    el("span", { class: "kicker" }, "click-to-save staging"),
  ]));
  card.appendChild(el("p", { class: "hint" },
    "Pair matches, record ledgers and explorer counts saved from the Spreadsheet " +
    "tab. These fill the “Contact matches”, “Pair records” and “Frequency counts” " +
    "sheets of the workbook."));

  const slot = el("div");
  card.appendChild(slot);

  const load = async () => {
    clear(slot);
    slot.appendChild(loading());
    let matches;
    let tallies;
    let ledgers;
    try {
      [matches, tallies, ledgers] = await Promise.all([
        api.savedMatches(), api.savedTallies(), api.savedLedgers()]);
    } catch (e) {
      clear(slot);
      slot.appendChild(msg(e.message));
      return;
    }
    clear(slot);
    if (matches.length === 0 && tallies.length === 0 && ledgers.length === 0) {
      slot.appendChild(el("div", { class: "empty" },
        "Nothing saved yet. Use “Save to export” on a pair comparison, a record " +
        "ledger, or a count in the Spreadsheet tab."));
      return;
    }

    const row = (text, dimText, onDelete) => {
      const del = el("button", { class: "btn btn-sm btn-danger" }, "Remove");
      del.addEventListener("click", () => confirmInline(del, onDelete, "Remove?"));
      return el("div", { class: "saved-item" }, [
        el("div", {}, [
          el("div", { class: "data" }, text),
          el("div", { class: "dim" }, dimText),
        ]),
        el("div", { class: "form-actions" }, [del]),
      ]);
    };

    if (matches.length) {
      slot.appendChild(el("h4", {}, `Pair matches (${matches.length})`));
      for (const m of matches) {
        const pair = m.result.pair;
        const summary = m.result.findings.length === 0
          ? "no link found"
          : m.result.findings.map((f) => `${f.label}: ${f.strength}`).join(" · ");
        slot.appendChild(row(
          `${pair.target_a.name} (${pair.target_a.phone_number}) ↔ ` +
          `${pair.target_b.name} (${pair.target_b.phone_number}) — ${m.dataset_name}`,
          summary,
          async () => {
            try {
              await api.deleteSavedMatch(m.id);
              toast("Saved pair match removed");
            } catch (e) { toast(e.message, "error"); }
            load();
          }));
      }
    }
    if (ledgers.length) {
      slot.appendChild(el("h4", {}, `Record ledgers (${ledgers.length})`));
      for (const l of ledgers) {
        const p = l.pair;
        slot.appendChild(row(
          `${p.target_a.name} (${p.target_a.phone_number}) ↔ ` +
          `${p.target_b.name} (${p.target_b.phone_number}) — ${l.dataset_name}`,
          `${l.row_count} record(s) · saved ${fmtDate(l.created_at)}`,
          async () => {
            try {
              await api.deleteSavedLedger(l.id);
              toast("Saved ledger removed");
            } catch (e) { toast(e.message, "error"); }
            load();
          }));
      }
    }
    if (tallies.length) {
      slot.appendChild(el("h4", {}, `Frequency counts (${tallies.length})`));
      for (const t of tallies) {
        slot.appendChild(row(
          t.filter_label,
          `${t.tally.total_records} record(s) · saved ${fmtDate(t.created_at)}`,
          async () => {
            try {
              await api.deleteSavedTally(t.id);
              toast("Saved count removed");
            } catch (e) { toast(e.message, "error"); }
            load();
          }));
      }
    }
  };

  await load();
  return card;
}
