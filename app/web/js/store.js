// Tiny in-memory app state. Re-bootstrapped on launch via GET /api/status; the
// URL hash carries the durable navigation context (which dataset/target), so a
// reload lands on the right screen and just re-fetches.

export const store = {
  username: null,        // set on login/setup, cleared on logout
  accountExists: null,   // from /api/status
  activeDataset: null,   // {id, name} — set when entering a dataset's targets
  // Cache of the last analyze() payload, so RESULTS can render immediately after
  // an analyze without a second round-trip (falls back to GET result on reload).
  lastResult: null,
};

export function reset() {
  store.username = null;
  store.activeDataset = null;
  store.lastResult = null;
}
