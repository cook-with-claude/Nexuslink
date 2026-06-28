// Bottom status bar: connection state, active dataset, live counts, clock.
// Rebuilt by shell() on every navigation, so the clock interval is tracked at
// module scope and cleared on each render to avoid stacking timers. Counts are
// pushed in by screens (no polling loop) — see setStatusCounts().

import { el } from "./components.js";
import { store } from "./store.js";

let refs = null;
let timer = null;

function pad(n) { return String(n).padStart(2, "0"); }
function nowHHMM() { const d = new Date(); return `${pad(d.getHours())}:${pad(d.getMinutes())}`; }

export function renderStatusbar() {
  const dot = el("span", { class: "status-dot" });
  const conn = el("span", {}, "Connected");
  const ds = el("span", { class: "status-ds" }, store.activeDataset ? store.activeDataset.name : "—");
  const counts = el("span", { class: "status-counts mono" }, "—");
  const clock = el("span", { class: "status-clock mono" }, nowHHMM());

  const bar = el("footer", { class: "statusbar", role: "status", "aria-live": "off" }, [
    el("div", { class: "seg" }, [dot, conn, el("span", { class: "sep" }, "·"), ds]),
    el("div", { class: "seg" }, [counts, el("span", { class: "sep" }, "·"), clock]),
  ]);

  refs = { dot, conn, ds, counts, clock };
  applyCounts();

  if (timer) clearInterval(timer);
  timer = setInterval(() => {
    if (refs && document.body.contains(refs.clock)) refs.clock.textContent = nowHHMM();
  }, 30000);

  return bar;
}

function applyCounts() {
  if (!refs) return;
  const c = store.counts;
  refs.counts.textContent = c ? `${c.datasets} datasets · ${c.targets} targets` : "—";
}

// Screens call this after they fetch datasets/targets, so the bar reflects the
// real totals without the status bar polling on its own.
export function setStatusCounts(datasets, targets) {
  store.counts = { datasets, targets };
  applyCounts();
}

export function setConnection(ok) {
  if (!refs) return;
  refs.dot.classList.toggle("off", !ok);
  refs.conn.textContent = ok ? "Connected" : "Disconnected";
}

export function setActiveDatasetLabel(name) {
  if (refs) refs.ds.textContent = name || "—";
}
