// Tiny in-memory app state. Re-bootstrapped on launch via GET /api/status; the
// URL hash carries the durable navigation context (which dataset/target), so a
// reload lands on the right screen and just re-fetches.

export const store = {
  // The auth GUARD keys off `authenticated`, not `username`: GET /api/status
  // reports authenticated:true after a reload (live session cookie) but does NOT
  // return the username, so keying the guard off username would bounce a still
  // logged-in user to login. username is display-only and may be null on reload.
  authenticated: false,  // from /api/status on boot; set true on login/setup
  username: null,        // display name; set on login/setup, may be null after reload
  accountExists: null,   // from /api/status
  activeDataset: null,   // {id, name} — set when entering a dataset's targets
  // Cache of the last analyze() payload, so RESULTS can render immediately after
  // an analyze without a second round-trip (falls back to GET result on reload).
  lastResult: null,
};

export function reset() {
  store.authenticated = false;
  store.username = null;
  store.activeDataset = null;
  store.lastResult = null;
}
