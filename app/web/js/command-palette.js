// Command palette (Ctrl/Cmd+K). A focus-trapped overlay with a single input and
// a filtered command list: static navigation/actions plus one entry per dataset
// (loaded lazily on open). Keyboard: Up/Down move, Enter runs, Esc closes; Tab is
// trapped so focus stays in the input. Only available while authenticated.

import { el, clear } from "./components.js";
import { store, reset } from "./store.js";
import { api } from "./api.js";

let overlay = null;

function staticCommands() {
  return [
    { label: "Go to Dashboard", hint: "go", run: () => (location.hash = "#/dashboard") },
    { label: "Go to Datasets", hint: "go", run: () => (location.hash = "#/datasets") },
    { label: "Import dataset", hint: "action", run: () => (location.hash = "#/import") },
    { label: "Change password", hint: "go", run: () => (location.hash = "#/change-password") },
    {
      label: "Log out", hint: "action", run: async () => {
        try { await api.logout(); } catch { /* drop client state regardless */ }
        reset();
        location.hash = "#/login";
      },
    },
  ];
}

function open() {
  if (overlay || !store.authenticated) return;

  const input = el("input", { type: "text", placeholder: "Type a command or dataset…", "aria-label": "Command palette" });
  const list = el("div", { class: "cmdk-list", role: "listbox" });
  const box = el("div", { class: "cmdk" }, [input, list]);
  overlay = el("div", {
    class: "cmdk-overlay",
    role: "dialog",
    "aria-modal": "true",
    onclick: (e) => { if (e.target === overlay) close(); },
  }, [box]);
  document.body.appendChild(overlay);

  let commands = staticCommands();
  let visible = [];
  let sel = 0;

  const renderList = () => {
    const q = input.value.trim().toLowerCase();
    visible = q ? commands.filter((c) => c.label.toLowerCase().includes(q)) : commands.slice();
    if (sel >= visible.length) sel = Math.max(0, visible.length - 1);
    clear(list);
    if (visible.length === 0) {
      list.appendChild(el("div", { class: "cmdk-empty" }, "No matches"));
      return;
    }
    visible.forEach((c, i) => {
      list.appendChild(el("div", {
        class: "cmdk-item" + (i === sel ? " sel" : ""),
        role: "option",
        "aria-selected": i === sel ? "true" : "false",
        onclick: () => { const run = c.run; close(); run(); },
      }, [el("span", { class: "label" }, c.label), el("span", { class: "hint" }, c.hint)]));
    });
  };

  renderList();

  // Lazily append per-dataset "open targets" commands.
  api.datasets().then((ds) => {
    if (!overlay) return;
    commands = commands.concat(ds.map((d) => ({
      label: `Dataset: ${d.name}`,
      hint: "open",
      run: () => { store.activeDataset = { id: d.id, name: d.name }; location.hash = `#/datasets/${d.id}/targets`; },
    })));
    renderList();
  }).catch(() => { /* palette still works with static commands */ });

  input.addEventListener("input", () => { sel = 0; renderList(); });
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); sel = Math.min(sel + 1, visible.length - 1); renderList(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); sel = Math.max(sel - 1, 0); renderList(); }
    else if (e.key === "Enter") { e.preventDefault(); const c = visible[sel]; if (c) { const run = c.run; close(); run(); } }
    else if (e.key === "Escape") { e.preventDefault(); close(); }
    else if (e.key === "Tab") { e.preventDefault(); }   // trap focus in the input
  });

  input.focus();
}

function close() {
  if (overlay) { overlay.remove(); overlay = null; }
}

export function initCommandPalette() {
  window.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && (e.key === "k" || e.key === "K")) {
      e.preventDefault();
      overlay ? close() : open();
    }
  });
}

export function openCommandPalette() { open(); }
