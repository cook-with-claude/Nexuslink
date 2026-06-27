// Hash router + auth guard. Routes are registered as patterns; a leading "*"
// route is the auth gate. The router re-checks /api/status on each navigation so
// a stale session always lands on login.

import { api } from "./api.js";
import { store } from "./store.js";
import { el, clear } from "./components.js";

const routes = [];

// register(pattern, handler) where pattern is "#/datasets/:id/targets" style.
export function register(pattern, handler, { auth = true } = {}) {
  const keys = [];
  const rx = new RegExp(
    "^" + pattern.replace(/:[^/]+/g, (m) => { keys.push(m.slice(1)); return "([^/]+)"; }) + "$",
  );
  routes.push({ rx, keys, handler, auth });
}

function match(hash) {
  const path = hash.replace(/^#/, "") || "/";
  for (const r of routes) {
    const m = r.rx.exec("#" + path);
    if (m) {
      const params = {};
      r.keys.forEach((k, i) => (params[k] = decodeURIComponent(m[i + 1])));
      return { route: r, params };
    }
  }
  return null;
}

let booting = true;

async function dispatch() {
  const app = document.getElementById("app");
  const hash = location.hash || "#/";

  // Bootstrap auth state once per load, then trust the in-memory store +
  // the api.js 401 redirect for the rest of the session.
  if (booting) {
    try {
      const s = await api.status();
      store.accountExists = s.account_exists;
      if (!s.authenticated) store.username = null;
    } catch {
      // status is unauthenticated/public; if it fails we still render login.
    }
    booting = false;
  }

  const found = match(hash);

  // Default route -> dashboard if logged in, else login.
  if (!found || hash === "#/" || hash === "#") {
    location.hash = store.username ? "#/dashboard" : "#/login";
    return;
  }

  // Auth guard: a protected route with no known user -> login.
  if (found.route.auth && !store.username) {
    location.hash = "#/login";
    return;
  }
  // Already logged in but sitting on login -> dashboard.
  if (!found.route.auth && store.username && hash.startsWith("#/login")) {
    location.hash = "#/dashboard";
    return;
  }

  clear(app);
  try {
    await found.route.handler(app, found.params);
  } catch (e) {
    clear(app);
    app.appendChild(el("div", { class: "page" }, [
      el("div", { class: "msg msg-error" }, e.message || "Something went wrong."),
    ]));
  }
}

export function startRouter() {
  window.addEventListener("hashchange", dispatch);
  dispatch();
}

export function go(hash) { location.hash = hash; }
