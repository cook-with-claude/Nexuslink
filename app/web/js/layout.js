// Shared chrome: the top nav rendered on every authenticated screen. Returns a
// .page container the caller fills with screen content.

import { el } from "./components.js";
import { store } from "./store.js";
import { api } from "./api.js";
import { reset } from "./store.js";

const NAV = [
  ["#/dashboard", "Dashboard"],
  ["#/datasets", "Datasets"],
];

export function shell(app, activeHash) {
  const links = NAV.map(([href, label]) =>
    el("a", { href, class: location.hash.startsWith(href) ? "active" : "" }, label),
  );

  const logout = el("button", { class: "link", onclick: async () => {
    try { await api.logout(); } catch { /* even if it fails, drop client state */ }
    reset();
    location.hash = "#/login";
  } }, "Logout");

  const nav = el("nav", { class: "topnav" }, [
    el("span", { class: "brand" }, "LA PASSION"),
    ...links,
    el("a", { href: "#/change-password" }, "Password"),
    el("span", { class: "spacer" }),
    el("span", { class: "user mono" }, store.username || ""),
    el("span", {}, " "),
    logout,
  ]);

  const page = el("div", { class: "page" });
  app.appendChild(nav);
  app.appendChild(page);
  return page;
}
