# Phase 2A — Backend Foundation: Design Spec

**Date:** 2026-06-24
**Status:** Approved design (pre-implementation)
**Author:** Claude Code (branch `claude/phase2a-design`)

## 0. Hard constraints (override everything below)

- **All data is synthetic.** This system never touches real telecom data or real
  individuals under any framing. Any decision that only makes sense against real
  data is out of scope and must be flagged, not built.
- **Phase 1 is frozen.** No file under `phase1_cdr/` is edited. The backend only
  *imports and calls* Phase 1 functions/constants. Phase 1's tag `v1.0-phase1`
  must still pass its suite (34 validation checks + 18 unit tests) at session end.
- **This is a backend-only session.** No HTML/CSS/JS beyond a one-line backend
  status placeholder. The real UI is Phase 2B (separate session).
- **No invented test data.** Tests reuse Phase 1's existing synthetic fixtures
  (`sample_data.csv`, users A–E).

## 1. Scope

Phase 2A delivers the backend foundation for a single-user desktop app that runs
Phase 1 detection on imported synthetic CDR data:

1. Desktop window via PyWebView pointed at a local Flask server (no browser).
2. Single-account auth (username/password, bcrypt-hashed; sessions).
3. Excel (`.xlsx`) import pipeline with strict validation + a skip report.
4. Target management (named reference to a phone_number within a dataset).
5. Phase 1 detection integration via a thin bridge.
6. A clean JSON API for Phase 2B to consume.
7. Security: encrypted-on-disk SQLite, envelope key management, audit log.

### Resolved decisions (from brainstorming)

| # | Decision | Choice |
|---|---|---|
| 1 | CDR schema | **Full 9-column** schema (matches `v1.0-phase1`; frequent-contacts works) |
| 2 | Account model | **Single account** per install |
| 3 | SQLite encryption library | **`sqlcipher3-wheels`** (prebuilt Windows wheels, SQLCipher 4, self-contained) |
| 4 | DB key management | **Envelope**: random DB key wrapped by a password-derived KEK |
| 5 | First-run account creation | **`POST /api/setup`** endpoint (active only while no account exists) |
| 6 | change-password endpoint | **Included** this session |
| 7 | Failed-login lockout | **Skipped** (YAGNI for localhost single-user) |
| 8 | Delete-dataset endpoint | **Included** (cleanup completeness) |
| 9 | Analysis response | **Full gate trace** exposed (explainability), not just headline confidence |

### Library finding (Windows, verified 2026-06-24)

- `sqlcipher3-wheels` — prebuilt `win_amd64` wheels, Python 3.8–3.14 (3.11 ✓),
  bundles SQLCipher 4 + OpenSSL, self-contained, latest 0.5.7 (Jan 2026).
  `pip install` works on Windows with no external toolchain.
- `sqlcipher3-binary` (official) — Linux-only wheels; unusable on Windows.
- `pysqlcipher3` — requires building libsqlcipher + OpenSSL + Visual Studio C++.
- Sources: https://pypi.org/project/sqlcipher3-wheels/ ,
  https://pypi.org/project/sqlcipher3-binary/ ,
  https://github.com/silverback97/pysqlcipher3-for-windows

## 2. Project structure

Phase 1 stays untouched; the new backend is a sibling package.

```
la passion/
  phase1_cdr/              # UNTOUCHED — imported read-only
  app/                     # new Flask backend package
    __init__.py            #  app factory: create_app()
    config.py              #  paths + tunables, NO secrets
    crypto.py              #  envelope: scrypt KDF, AES-GCM wrap/unwrap, bcrypt helpers
    storage.py             #  SQLCipher connect (PRAGMA key), schema init, query helpers
    auth.py                #  blueprint: /setup /login /logout /change-password + @login_required
    imports.py             #  blueprint: .xlsx upload + validation pipeline
    targets.py             #  blueprint: target CRUD
    analysis.py            #  blueprint: run detection on a target
    detection_bridge.py    #  the ONLY seam to phase1_cdr (DB rows -> DataFrame -> detectors)
    validation.py          #  per-row CDR checks (reuses phase1 loader constants)
    audit.py               #  audit-log writer
  main.py                  # entry point: Flask thread + PyWebView window
  tests/phase2a/           # new tests (Phase 1 tests stay in phase1_cdr/tests)
  requirements.txt         # extended
```

**App-data location (never in repo):** the encrypted DB `cdr.db` and the
non-secret `auth.json` sidecar live in an app-data dir — default
`%LOCALAPPDATA%\LaPassionCDR\`, overridable via the `APP_DATA_DIR` env var
(tests point it at a temp dir). Gitignored if ever in-tree.

**New dependencies:** `flask`, `pywebview`, `bcrypt`, `cryptography`
(AES-GCM + scrypt), `sqlcipher3-wheels`. Existing `pandas`/`openpyxl` reused.

**Phase 1 import seam:** `detection_bridge.py` is the *single* file importing from
`phase1_cdr` — the five detectors (`detect_home`, `detect_work`,
`detect_frequent_areas`, `detect_frequent_confidence`, `detect_frequent_contacts`)
plus the read-only constants `VALID_CALL_TYPES` / `REQUIRED_COLUMNS` (so the
importer's validation never drifts from Phase 1).

## 3. App lifecycle (PyWebView + Flask)

1. `main.py` builds the Flask app and starts it via
   `werkzeug.serving.make_server` bound to `127.0.0.1:0` (OS picks a free
   ephemeral port) on a **daemon background thread**. `make_server` (not
   `app.run()`) gives a real server handle with `.shutdown()`.
2. Main thread waits until the server is listening (polls `/api/health`), then
   `webview.create_window(...)` → `webview.start()` opens the desktop window at
   `http://127.0.0.1:<port>/`. No browser.
3. The window shows a one-line backend-status placeholder (`/api/health` JSON).
   Real UI is Phase 2B.
4. On window close, `webview.start()` returns → `server.shutdown()` → process
   exits; the daemon thread dies with it.

## 4. Security model

### 4.1 Envelope encryption (`crypto.py`)

`auth.json` sidecar holds only **non-secret** material:

```
auth.json: { username, bcrypt_hash, kdf_salt, db_key_nonce, wrapped_db_key, created_at }
```

- **Setup** (first run): generate random 256-bit `db_key` (`os.urandom(32)`) →
  derive `kek = scrypt(password, kdf_salt)` → `wrapped_db_key =
  AES-GCM_encrypt(kek, db_key)` → bcrypt-hash the password → write `auth.json` →
  create the encrypted DB with `PRAGMA key`. The raw `db_key` is never written to
  disk; only its wrapped form is.
- **Login**: `bcrypt.checkpw` (auth gate) → re-derive `kek` → AES-GCM unwrap →
  `db_key` → open SQLCipher with it. Wrong password fails bcrypt *and* can't
  unwrap (defence in depth).
- **Change password**: re-derive a new `kek`, re-wrap the *same* `db_key`,
  rewrite `auth.json`. The DB itself is never re-encrypted.

**Why this meets "encrypted on disk, not app-level":** SQLCipher does transparent
page-level AES-256 over the whole `.db`. Without the password the `db_key` is
unrecoverable, so the file is ciphertext at rest. A test proves plain `sqlite3`
cannot open the file.

**KDF split:** scrypt (via `cryptography`) for the *encryption* KEK; bcrypt for
the *password verifier* — two functions for two jobs. The SQLCipher key passed in
is the raw 32-byte `db_key` (`PRAGMA key="x'<hex>'"`), so SQLCipher's own KDF is
not relied on for the password.

### 4.2 Sessions

- Flask server-side signed-cookie sessions, gated by `@login_required` on every
  route except `/api/health`, `/api/status`, `/api/setup`, `/api/login`.
- `SECRET_KEY = os.urandom(32)` generated **per process launch** (no hardcoded
  secret; sessions invalidate on restart — fine for a desktop app).
- Cookie flags: `HttpOnly`, `SameSite=Strict`. `Secure` omitted (plain-HTTP
  localhost; the webview is the only client).
- **CSRF**: low risk (no browser, `SameSite=Strict`, same-origin webview); as a
  hardening touch, state-changing requests require `Content-Type:
  application/json` and form-encoded cross-origin posts are rejected.
- The in-memory `db_key` lives only in the server process for the session and is
  dropped on logout/shutdown.

### 4.3 Audit log

Writes a row for: `SETUP`, `LOGIN_SUCCESS`, `LOGIN_FAIL`, `LOGOUT`, `IMPORT`,
`TARGET_CREATE`, `TARGET_DELETE`, `ANALYSIS`, `CHANGE_PASSWORD` — each with
username + UTC timestamp + a small detail blob. Passwords/keys are never logged.

### 4.4 Other security requirements

- Parameterized queries only; no raw SQL string interpolation.
- No hardcoded secrets/keys/credentials anywhere in code.
- `PRAGMA foreign_keys = ON` on every connection.

## 5. Database schema

All tables live inside the SQLCipher-encrypted `cdr.db`. Credentials are **not**
here (they're in `auth.json`, needed before the DB can open).

```sql
datasets (
  id            INTEGER PRIMARY KEY,
  name          TEXT NOT NULL,
  filename      TEXT NOT NULL,
  imported_at   TEXT NOT NULL,           -- ISO-8601 UTC
  row_count     INTEGER NOT NULL,
  skipped_count INTEGER NOT NULL
);

cdr_records (
  id               INTEGER PRIMARY KEY,
  dataset_id       INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
  phone_number     TEXT NOT NULL,
  imei             TEXT,
  area             TEXT NOT NULL,
  timestamp        TEXT NOT NULL,        -- ISO-8601; parsed to datetime in the bridge
  call_type        INTEGER NOT NULL,     -- one of {1,2,11,22}
  duration_seconds INTEGER NOT NULL,     -- >= 0
  other_party      TEXT,
  other_imei       TEXT,
  other_area       TEXT
);
CREATE INDEX idx_records_dataset_phone ON cdr_records(dataset_id, phone_number);

targets (
  id           INTEGER PRIMARY KEY,
  name         TEXT NOT NULL,            -- display label only, NOT an identity key
  dataset_id   INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
  phone_number TEXT NOT NULL,
  created_at   TEXT NOT NULL,
  UNIQUE(dataset_id, phone_number)       -- one target per phone per dataset, full stop
);

analysis_results (
  id          INTEGER PRIMARY KEY,
  target_id   INTEGER NOT NULL REFERENCES targets(id) ON DELETE CASCADE,
  created_at  TEXT NOT NULL,
  result_json TEXT NOT NULL              -- serialized home/work/frequent/contacts
);

audit_log (
  id         INTEGER PRIMARY KEY,
  ts         TEXT NOT NULL,              -- ISO-8601 UTC
  username   TEXT NOT NULL,
  event_type TEXT NOT NULL,
  detail     TEXT                        -- small JSON blob, never secrets
);
```

Decisions baked in:
- `timestamp` stored as ISO-8601 text (UTC), parsed to pandas datetime in the
  bridge. Portable and debuggable.
- `ON DELETE CASCADE` so deleting a dataset cleans its records/targets/results;
  deleting a target cleans its results.
- Nullable columns are exactly Phase 1's optional-value fields (`imei`,
  `other_party`, `other_imei`, `other_area`); the five Phase-1-critical fields are
  `NOT NULL` and validated on import.
- Analysis history retained (one row per run); the API returns the latest.

## 6. JSON API

Conventions: all routes under `/api`. State-changing requests require
`Content-Type: application/json` (except the multipart import). Envelope:
success `{"ok": true, "data": {...}}`, error `{"ok": false, "error": {"code",
"message"}}` with a proper HTTP status. Every route except the four public ones
requires a valid session.

### Public (no auth)

| Method | Route | Body / returns |
|---|---|---|
| `GET` | `/api/health` | `{status:"ok"}` — startup readiness + placeholder |
| `GET` | `/api/status` | `{account_exists, authenticated}` |
| `POST` | `/api/setup` | `{username, password}` → 201; **409** if account exists |
| `POST` | `/api/login` | `{username, password}` → 200 sets session; **401** bad creds |

### Authenticated

| Method | Route | Body / returns |
|---|---|---|
| `POST` | `/api/logout` | clears session, drops db_key → `{ok}` |
| `POST` | `/api/change-password` | `{old_password, new_password}` → re-wraps db_key; **401** if old wrong |
| `POST` | `/api/imports` | **multipart** `.xlsx` (+ `name`) → `{dataset_id, imported, skipped, skipped_reasons:[{row, reason}]}` |
| `GET` | `/api/datasets` | `[{id, name, filename, imported_at, row_count, skipped_count}]` |
| `GET` | `/api/datasets/<id>/phone-numbers` | distinct numbers + counts |
| `DELETE` | `/api/datasets/<id>` | cascade-delete → `{ok}` |
| `POST` | `/api/targets` | `{name, dataset_id, phone_number}` → 201; 404 if dataset/number absent; **409** if a target already exists for that `(dataset_id, phone_number)` |
| `GET` | `/api/targets` | list targets |
| `DELETE` | `/api/targets/<id>` | delete → `{ok}` |
| `POST` | `/api/targets/<id>/analyze` | run detection, store + return result |
| `GET` | `/api/targets/<id>/result` | latest stored result, or 404 |

`/api/imports` is the only multipart endpoint and never crashes on a bad file:
unreadable/corrupt/non-xlsx → `400 code:"BAD_FILE"`; missing columns → `400
code:"SCHEMA_MISMATCH"` naming them. Row-level problems don't fail the import —
they're counted and itemized in `skipped_reasons`.

### Analysis response shape (`data` for `/analyze` and `/result`)

```json
{
  "target": {"id": 1, "name": "...", "phone_number": "01000001"},
  "analyzed_at": "2026-06-24T...Z",
  "home":     {"area": "Hamra", "confidence": "High", "confidence_label": "High",
               "near_tie": false, "alternatives": [],
               "supporting_records": 560, "total_window_records": 640,
               "share": 0.875, "closeness": 0.09, "density": 0.55,
               "gates": {"N":"High","share":"High","closeness":"High","density":"High"}},
  "work":     { "...same shape..." },
  "frequent_areas":    [{"area":"Hamra","count":700,"share":0.66}],
  "frequent_areas_confidence": {"area":"Hamra","confidence":"High","share":0.66},
  "frequent_contacts": [{"number":"03200101","total":210,
                         "call_out":53,"call_in":50,"sms_out":61,"sms_in":46}]
}
```

A faithful 1:1 serialization of Phase 1's `DetectionResult` / `ContactRank`
dataclasses — the bridge maps fields to JSON, no reinterpretation. `top_n`
defaults to 5; a `?top_n=` query param overrides both frequent lists.

## 7. Detection bridge (`detection_bridge.py`)

The single seam to Phase 1 (no Phase 1 edits):

1. Query `cdr_records` for the target's `(dataset_id, phone_number)`
   (parameterized).
2. Build a pandas DataFrame with the 9 columns; `pd.to_datetime(timestamp)`, cast
   `call_type`/`duration_seconds` to int — the exact frame shape Phase 1's
   detectors expect (equivalent to `loader.load_cdr` output, but DB-sourced).
3. Call the five detectors and serialize their dataclasses to the §6 JSON shape.
4. **Equivalence guarantee:** the bridge returns the same output as calling Phase
   1 directly on the same records — storing-then-reading through SQLCipher cannot
   silently alter results (asserted by a test).

## 8. Test plan (`tests/phase2a/`, pytest + Flask test client; `APP_DATA_DIR`→`tmp_path`)

- **crypto** — wrap/unwrap round-trips; wrong password fails to unwrap (raises);
  bcrypt verify true/false; change-password re-wraps the *same* db_key (decrypts
  to identical bytes).
- **on-disk encryption (headline security test)** — after setup, raw `cdr.db`
  bytes lack the SQLite magic header and plain `sqlite3.connect()` without the key
  cannot read it; SQLCipher *with* the key can. Concrete proof of "encrypted on
  disk."
- **auth/sessions** — setup creates account; second setup → 409; login good/bad
  (200/401); protected route with no session → 401; logout then protected → 401;
  change-password old-wrong → 401, then login with new password works.
- **import pipeline** — valid file → correct `imported`/`skipped`; missing column
  → `SCHEMA_MISMATCH` naming columns; rows with bad `call_type` / unparseable
  `timestamp` / negative `duration` → skipped with itemized reasons, valid rows
  stored; corrupt/non-xlsx → `BAD_FILE`, no crash.
- **targets** — create/list/delete; create against nonexistent dataset or
  phone_number → 404; creating a second target for an already-targeted
  `(dataset_id, phone_number)` → 409 (even with a different name); cascade delete
  removes targets + results.
- **analysis** — run on a target → full response shape; **bridge equivalence**:
  equals a direct Phase 1 call on the same rows.
- **audit** — login/import/analysis/target/setup events each land a row with
  username + timestamp; no secret material in any `detail`.
- **Phase 1 regression** — the existing `phase1_cdr` suite (34 checks + 18 unit
  tests) still passes (Phase 1 untouched).

**Test data — reuses Phase 1 synthetic fixtures (no invented data):** a fixture
converts Phase 1's existing `sample_data.csv` (users A–E) into a temp `.xlsx` and
feeds it through the importer, so import/target/analysis tests run on the same
synthetic users Phase 1 already validates, and the bridge is asserted to reproduce
Phase 1's known A–E expectations end-to-end.

## 9. Out of scope (Phase 2B or later)

- Any real UI (HTML/CSS/JS) beyond the one-line status placeholder.
- Multi-account support, per-user data isolation, OS-keystore key storage.
- Failed-login lockout/throttling.
- Editing any Phase 1 algorithm code.
