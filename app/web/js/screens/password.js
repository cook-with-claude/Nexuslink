// CHANGE PASSWORD. Client-side match check before submit. Both success and error
// stay on the page inline. API-MISMATCH #7: a 401 here = wrong current password
// (local, not a redirect — api.js skips the redirect for /api/change-password).
// API-MISMATCH #12: bcrypt 72-byte limit surfaces as a 400 message inline.

import { api, ApiError } from "../api.js";
import { shell } from "../layout.js";
import { el, clear, msg } from "../components.js";

export async function passwordScreen(app) {
  const page = shell(app);
  page.appendChild(el("h1", {}, "Change password"));

  const card = el("div", { class: "card auth-card" });
  page.appendChild(card);

  const cur = el("input", { type: "password", id: "cur", autocomplete: "current-password" });
  const nw = el("input", { type: "password", id: "nw", autocomplete: "new-password" });
  const cf = el("input", { type: "password", id: "cf", autocomplete: "new-password" });
  const slot = el("div");
  const btn = el("button", { class: "btn btn-primary", type: "submit" }, "Update password");

  const form = el("form", {}, [
    el("label", { for: "cur" }, "Current password"), cur,
    el("label", { for: "nw" }, "New password"), nw,
    el("label", { for: "cf" }, "Confirm new password"), cf,
    slot,
    el("div", { class: "form-actions" }, [btn]),
  ]);
  card.appendChild(form);

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    clear(slot);
    if (!cur.value || !nw.value || !cf.value) { slot.appendChild(msg("All fields are required.")); return; }
    if (nw.value !== cf.value) { slot.appendChild(msg("New passwords do not match.")); return; }
    btn.disabled = true;
    try {
      await api.changePassword(cur.value, nw.value);
      form.reset();
      slot.appendChild(msg("Password updated.", "ok"));
    } catch (err) {
      if (err instanceof ApiError && err.code === "SESSION_EXPIRED") return;
      const text = err instanceof ApiError
        ? (err.status === 401 ? "Current password is incorrect." : err.message)
        : "Could not change password.";
      slot.appendChild(msg(text));
    } finally {
      btn.disabled = false;
    }
  });

  cur.focus();
}
