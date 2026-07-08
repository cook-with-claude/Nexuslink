// Shared chrome: the analyst-workstation shell rendered on every authenticated
// screen — a left icon+label rail, a top context/breadcrumb bar, a full-bleed
// scrolling content region, and a bottom status bar. Returns the content element
// plus setCrumb()/setActions() so each screen drives the context bar instead of
// rendering its own page header.

import { el, clear, icon } from "./components.js";
import { store, reset } from "./store.js";
import { api } from "./api.js";
import { renderStatusbar } from "./statusbar.js";

// [hash, label, icon]
const NAV = [
  ["#/dashboard", "Dashboard", "dashboard"],
  ["#/datasets", "Datasets", "database"],
  ["#/spreadsheet", "Spreadsheet", "table"],
];

const RAIL_KEY = "lp-rail-collapsed";

// Active state keys off the FIRST path segment, so #/datasets stays highlighted
// on #/datasets/:id/targets without falsely matching unrelated routes (fixes the
// old location.hash.startsWith bug).
function routeSegment() {
  const h = (location.hash || "").replace(/^#\/?/, "");
  return "#/" + (h.split("/")[0] || "");
}

export function shell(app) {
  // Clear first so an in-place refresh (a screen re-invoking itself after a
  // delete/add, not via the router) never stacks a second shell.
  clear(app);

  const shellEl = el("div", { class: "shell" });
  if (localStorage.getItem(RAIL_KEY) === "1") shellEl.classList.add("rail-collapsed");

  const seg = routeSegment();
  const navItem = (href, label, ic) => {
    const active = seg === href;
    return el("a", {
      href,
      class: "nav-item" + (active ? " active" : ""),
      "aria-current": active ? "page" : null,
      title: label,
    }, [icon(ic), el("span", { class: "label" }, label)]);
  };

  const collapseBtn = el("button", {
    class: "nav-item",
    type: "button",
    title: "Collapse sidebar",
    onclick: () => {
      shellEl.classList.toggle("rail-collapsed");
      localStorage.setItem(RAIL_KEY, shellEl.classList.contains("rail-collapsed") ? "1" : "0");
    },
  }, [icon("panel"), el("span", { class: "label" }, "Collapse")]);

  const logoutBtn = el("button", {
    class: "nav-item",
    type: "button",
    title: "Log out",
    onclick: async () => {
      try { await api.logout(); } catch { /* drop client state regardless */ }
      reset();
      location.hash = "#/login";
    },
  }, [icon("logout"), el("span", { class: "label" }, "Logout")]);

  const rail = el("nav", { class: "rail", "aria-label": "Primary" }, [
    el("div", { class: "rail-brand" }, [
      el("span", { class: "brand-mark" }, "NL"),
      el("span", { class: "label brand-name" }, "Nexuslink"),
    ]),
    el("div", { class: "rail-nav" }, NAV.map(([h, l, i]) => navItem(h, l, i))),
    el("div", { class: "rail-spacer" }),
    el("div", { class: "rail-foot" }, [
      collapseBtn,
      // App-wide export: in the always-visible rail so it is reachable from
      // every screen, not tied to any one tab.
      navItem("#/export", "Export", "download"),
      navItem("#/change-password", "Password", "lock"),
      logoutBtn,
    ]),
  ]);

  // context / breadcrumb bar
  const crumb = el("div", { class: "crumb" });
  const actions = el("div", { class: "context-actions" });
  const context = el("header", { class: "context" }, [crumb, actions]);

  const content = el("main", { class: "content" });
  const statusbar = renderStatusbar();

  shellEl.appendChild(rail);
  shellEl.appendChild(context);
  shellEl.appendChild(content);
  shellEl.appendChild(statusbar);
  app.appendChild(shellEl);

  // setCrumb(parts): parts is a string or array of strings/nodes. The last part
  // renders as the bold "leaf"; earlier parts are muted context separated by ▸.
  // A part may be { text, sub } to append a dim sub-label (e.g. a record count).
  const setCrumb = (parts) => {
    clear(crumb);
    const arr = [].concat(parts).filter((p) => p != null && p !== "");
    arr.forEach((part, i) => {
      if (i) crumb.appendChild(el("span", { class: "sep" }, "▸"));
      const last = i === arr.length - 1;
      if (typeof part === "string") {
        crumb.appendChild(el("span", { class: last ? "leaf" : "ctx" }, part));
      } else if (part && part.text !== undefined) {
        const span = el("span", { class: last ? "leaf" : "ctx" }, part.text);
        if (part.sub != null) span.appendChild(el("span", { class: "crumb-sub" }, part.sub));
        crumb.appendChild(span);
      } else {
        crumb.appendChild(part);   // already a node
      }
    });
  };

  const setActions = (nodes) => {
    clear(actions);
    [].concat(nodes || []).forEach((n) => n && actions.appendChild(n));
  };

  return { page: content, content, setCrumb, setActions };
}
