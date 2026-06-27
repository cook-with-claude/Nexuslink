// LOGIN / FIRST-RUN. On load, store.accountExists (from /api/status) decides
// between a setup form (create the first admin) and a login form. Errors render
// inline with fields preserved; no navigation. 401 here is LOCAL (api.js skips
// the redirect for /api/login).

import { api, ApiError } from "../api.js";
import { store } from "../store.js";
import { el, clear, msg } from "../components.js";

export async function loginScreen(app) {
  const isSetup = store.accountExists === false;
  const wrap = el("div", { class: "center-wrap" });
  const card = el("div", { class: "card auth-card" });
  wrap.appendChild(card);
  app.appendChild(wrap);

  const render = () => {
    clear(card);
    card.appendChild(el("h3", {}, isSetup ? "Create administrator account" : "Sign in"));
    if (isSetup) {
      card.appendChild(el("div", { class: "msg msg-info" },
        "No account exists yet. Set the administrator username and password."));
    }

    const u = el("input", { type: "text", id: "u", autocomplete: "username", placeholder: "username" });
    const p = el("input", { type: "password", id: "p", autocomplete: isSetup ? "new-password" : "current-password", placeholder: "password" });
    const errSlot = el("div");
    const btn = el("button", { class: "btn btn-primary", type: "submit" }, isSetup ? "Create account" : "Sign in");

    const form = el("form", {}, [
      el("label", { for: "u" }, "Username"), u,
      el("label", { for: "p" }, "Password"), p,
      errSlot,
      el("div", { class: "form-actions" }, [btn]),
    ]);

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      clear(errSlot);
      const username = u.value.trim();
      const password = p.value;
      if (!username || !password) {
        errSlot.appendChild(msg("Username and password are required."));
        return;
      }
      btn.disabled = true;
      try {
        const data = isSetup ? await api.setup(username, password) : await api.login(username, password);
        store.username = data.username;
        store.accountExists = true;
        location.hash = "#/dashboard";
      } catch (err) {
        btn.disabled = false;
        // bcrypt 72-byte limit (#12) and bad creds (401, #7) both land here inline.
        const text = err instanceof ApiError ? err.message : "Could not sign in.";
        errSlot.appendChild(msg(text));
        p.value = "";
        p.focus();
      }
    });

    card.appendChild(form);
    u.focus();
  };

  render();
}
