// Single fetch wrapper: unwraps the {ok,data}/{ok,error} envelope, throws a typed
// ApiError on ok:false, and centralizes the 401 policy.
//
// API-MISMATCH #7: a 401 means two different things. For the authenticated area
// it means "session gone" -> redirect to login. But /login and /change-password
// return 401 for *bad credentials / wrong current password*, which must be shown
// inline on the page. So the 401 redirect is skipped for those two endpoints
// (LOCAL_401_PATHS); callers there catch the ApiError and render it.

import { store } from "./store.js";

export class ApiError extends Error {
  constructor(code, message, status) {
    super(message || code || "request failed");
    this.code = code;
    this.status = status;
  }
}

const LOCAL_401_PATHS = new Set(["/api/login", "/api/change-password"]);

async function request(method, path, { json, form, query } = {}) {
  const opts = { method, headers: {} };

  if (form !== undefined) {
    // API-MISMATCH #11: multipart import must NOT set Content-Type manually —
    // the browser adds the multipart boundary. We only set JSON header below.
    opts.body = form;
  } else if (json !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(json);
  }

  let url = path;
  if (query) {
    const qs = new URLSearchParams(query).toString();
    if (qs) url += "?" + qs;
  }

  let res;
  try {
    res = await fetch(url, opts);
  } catch (e) {
    throw new ApiError("NETWORK", "could not reach the server", 0);
  }

  if (res.status === 401 && !LOCAL_401_PATHS.has(path)) {
    // Session expired / not authenticated in the app area -> drop client auth
    // state THEN bounce to login. Clearing first is what stops a redirect loop:
    // the guard keys off store.authenticated, so without this the login screen
    // would bounce straight back to dashboard, which 401s again.
    store.authenticated = false;
    store.username = null;
    if (location.hash !== "#/login") location.hash = "#/login";
    throw new ApiError("UNAUTHENTICATED", "login required", 401);
  }

  let body = null;
  try {
    body = await res.json();
  } catch {
    // Non-JSON error (e.g. a raw 413/500 HTML page) — synthesize from status.
    throw new ApiError("HTTP_" + res.status, "request failed (" + res.status + ")", res.status);
  }

  if (body && body.ok) return body.data;
  const e = (body && body.error) || {};
  throw new ApiError(e.code || "ERROR", e.message || "request failed", res.status);
}

export const api = {
  // unauthenticated / boot
  status: () => request("GET", "/api/status"),
  // auth
  setup: (username, password) => request("POST", "/api/setup", { json: { username, password } }),
  login: (username, password) => request("POST", "/api/login", { json: { username, password } }),
  logout: () => request("POST", "/api/logout", {}),
  changePassword: (old_password, new_password) =>
    request("POST", "/api/change-password", { json: { old_password, new_password } }),
  // datasets
  datasets: () => request("GET", "/api/datasets"),
  deleteDataset: (id) => request("DELETE", "/api/datasets/" + id, {}),
  phoneNumbers: (id) => request("GET", "/api/datasets/" + id + "/phone-numbers"),
  importDataset: (formData) => request("POST", "/api/imports", { form: formData }),
  // targets
  targets: () => request("GET", "/api/targets"),
  createTarget: (name, dataset_id, phone_number) =>
    // dataset_id sent as a Number — backend rejects string ids (API-MISMATCH #4).
    request("POST", "/api/targets", { json: { name, dataset_id: Number(dataset_id), phone_number } }),
  deleteTarget: (id) => request("DELETE", "/api/targets/" + id, {}),
  // analysis
  analyze: (id, top_n = 5) =>
    request("POST", "/api/targets/" + id + "/analyze", { query: { top_n } }),
  result: (id) => request("GET", "/api/targets/" + id + "/result"),
};
