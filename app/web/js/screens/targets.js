// TARGETS, scoped to one dataset. API-MISMATCH #3: /api/targets is global —
// filter by dataset_id client-side. API-MISMATCH #4: add-target phone is PICKED
// from /api/datasets/<id>/phone-numbers (backend 404s a phone not in the
// dataset), so the user can't hit the 404; dataset_id sent as a number.

import { api, ApiError } from "../api.js";
import { store } from "../store.js";
import { shell } from "../layout.js";
import { el, loading, clear, fmtDate, confirmInline, contextMenu, inlineRename, toast, msg, icon } from "../components.js";
import { setStatusCounts, setActiveDatasetLabel } from "../statusbar.js";

export async function targetsScreen(app, params) {
  const datasetId = Number(params.id);
  const { page, setCrumb, setActions } = shell(app);
  setActions([el("a", { href: "#/datasets", class: "btn" }, [icon("back"), "Datasets"])]);

  const body = el("div");
  body.appendChild(loading());
  page.appendChild(body);

  // Recover the dataset name (active store may be empty after a reload).
  let dsName = store.activeDataset && store.activeDataset.id === datasetId
    ? store.activeDataset.name : null;

  const [allTargets, datasets, phones] = await Promise.all([
    api.targets(),
    dsName ? Promise.resolve(null) : api.datasets(),
    api.phoneNumbers(datasetId),
  ]);
  if (!dsName && datasets) {
    const d = datasets.find((x) => x.id === datasetId);
    dsName = d ? d.name : `Dataset ${datasetId}`;
    store.activeDataset = { id: datasetId, name: dsName };
  }

  const targets = allTargets.filter((t) => t.dataset_id === datasetId);
  setActiveDatasetLabel(dsName);
  if (datasets) setStatusCounts(datasets.length, allTargets.length);
  else if (store.counts) setStatusCounts(store.counts.datasets, allTargets.length);
  clear(body);

  setCrumb([{ text: "Datasets", href: "#/datasets" },
            { text: dsName, sub: `${phones.length} numbers` }]);

  // --- add target form ---
  body.appendChild(addCard(app, datasetId, phones, targets));

  // --- targets table ---
  const listCard = el("div", { class: "card" });
  listCard.appendChild(el("h3", {}, "Targets in this dataset"));
  if (targets.length === 0) {
    listCard.appendChild(el("div", { class: "empty" }, "No targets yet. Add one above."));
  } else {
    const tbody = el("tbody");
    for (const t of targets) {
      const analyzeBtn = el("button", { class: "btn btn-sm btn-primary" }, "Analyze");
      analyzeBtn.addEventListener("click", async () => {
        analyzeBtn.disabled = true;
        clear(analyzeBtn);
        analyzeBtn.appendChild(el("span", { class: "spinner" }));
        try {
          const res = await api.analyze(t.id);
          store.lastResult = res;
          store.activeDataset = { id: datasetId, name: dsName };
          location.hash = `#/targets/${t.id}/result`;
        } catch (err) {
          analyzeBtn.disabled = false;
          analyzeBtn.textContent = "Analyze";
          toast(err.message, "error");
        }
      });

      const delBtn = el("button", { class: "btn btn-sm btn-danger" }, "Remove");
      delBtn.addEventListener("click", () => confirmInline(delBtn, async () => {
        try { await api.deleteTarget(t.id); toast("Target removed"); targetsScreen(app, params); }
        catch (err) { toast(err.message, "error"); }
      }, "Remove target?"));

      const nameCell = el("td", { class: "data" }, t.name);
      const startRename = () => inlineRename(nameCell, t.name, async (name) => {
        await api.renameTarget(t.id, name);
        toast("Target renamed");
        targetsScreen(app, params);
      });

      tbody.appendChild(el("tr", {
        oncontextmenu: (e) => contextMenu(e, [{ label: "Rename", onSelect: startRename }]),
      }, [
        nameCell,
        el("td", { class: "data" }, t.phone_number),
        el("td", { class: "data dim" }, fmtDate(t.created_at)),
        el("td", { class: "right" }, el("div", { class: "row-actions" }, [analyzeBtn, delBtn])),
      ]));
    }
    listCard.appendChild(el("table", {}, [
      el("thead", {}, el("tr", {}, [
        el("th", {}, "Name"), el("th", {}, "Phone"), el("th", {}, "Created"), el("th", { class: "right" }, "Actions"),
      ])),
      tbody,
    ]));
  }
  body.appendChild(listCard);
}

function addCard(app, datasetId, phones, existing) {
  const card = el("div", { class: "card" });
  card.appendChild(el("h3", {}, "Add target"));

  if (phones.length === 0) {
    card.appendChild(el("div", { class: "msg msg-info" }, "This dataset has no phone numbers to target."));
    return card;
  }

  const name = el("input", { type: "text", id: "tname", placeholder: "label for this subject" });
  const taken = new Set(existing.map((t) => t.phone_number));
  const picker = el("select", { id: "tphone", class: "mono" },
    [el("option", { value: "" }, "— select a phone number —")].concat(
      phones.map((p) => el("option", {
        value: p.phone_number,
        disabled: taken.has(p.phone_number) ? "disabled" : null,
      }, `${p.phone_number}  (${p.count} records)${taken.has(p.phone_number) ? " — already a target" : ""}`)),
    ));
  const errSlot = el("div");
  const btn = el("button", { class: "btn btn-primary", type: "submit" }, "Add target");

  const form = el("form", {}, [
    el("label", { for: "tname" }, "Name"), name,
    el("label", { for: "tphone" }, "Phone number (from dataset)"), picker,
    errSlot,
    el("div", { class: "form-actions" }, [btn]),
  ]);
  card.appendChild(form);

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    clear(errSlot);
    if (!name.value.trim()) { errSlot.appendChild(msg("A name is required.")); return; }
    if (!picker.value) { errSlot.appendChild(msg("Select a phone number.")); return; }
    btn.disabled = true;
    try {
      await api.createTarget(name.value.trim(), datasetId, picker.value);
      toast("Target added");
      targetsScreen(app, { id: String(datasetId) });
    } catch (err) {
      btn.disabled = false;
      // 409 -> already a target (#4)
      const text = err instanceof ApiError && err.status === 409
        ? "That phone is already a target in this dataset." : err.message;
      errSlot.appendChild(msg(text));
    }
  });

  return card;
}
