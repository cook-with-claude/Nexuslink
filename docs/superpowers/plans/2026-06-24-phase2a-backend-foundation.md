# Phase 2A — Backend Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Flask + PyWebView desktop backend that runs the frozen Phase 1 detection algorithm on imported synthetic CDR data, over a SQLCipher-encrypted SQLite database with single-account auth and an audit log.

**Architecture:** A new `app/` Flask package (sibling to the untouched `phase1_cdr/`) exposes a JSON API. The database is a SQLCipher file encrypted with a random 256-bit key that is itself wrapped (AES-GCM) by a scrypt-derived key-encryption-key from the login password; bcrypt is the password verifier. A single `detection_bridge.py` module is the only seam that imports Phase 1. `main.py` runs Flask on an ephemeral localhost port in a daemon thread and opens a PyWebView window at it.

**Tech Stack:** Python 3.11, Flask, PyWebView, `sqlcipher3-wheels` (SQLCipher 4), `bcrypt`, `cryptography` (scrypt + AES-GCM), pandas, openpyxl, pytest.

## Global Constraints

- **All data is synthetic.** Never build anything that only makes sense against real telecom data.
- **Phase 1 is frozen.** No file under `phase1_cdr/` may be edited. Only `app/detection_bridge.py` imports from it. Phase 1's suite (34 validation checks + 18 unit tests) must still pass at the end.
- **Backend only.** No HTML/CSS/JS beyond a one-line status placeholder served by `/api/health`.
- **No invented test data.** Tests reuse Phase 1's existing `phase1_cdr/sample_data.csv` (users A–E), converted to `.xlsx`.
- **CDR schema is the full 9 columns:** `phone_number, imei, area, timestamp, call_type, duration_seconds, other_party, other_imei, other_area`. Valid `call_type` ∈ `{1, 2, 11, 22}`.
- **Security:** bcrypt password hashing; SQLCipher page-level encryption (never a plaintext DB); no hardcoded secrets/keys; parameterized queries only; `PRAGMA foreign_keys = ON`; auth required on all routes except `/api/health`, `/api/status`, `/api/setup`, `/api/login`.
- **App-data location:** `cdr.db` + `auth.json` live in `APP_DATA_DIR` (env override) or default `%LOCALAPPDATA%\LaPassionCDR\`. Never committed.
- **Branch:** `claude/phase2a-design` (continue here per COLLAB.md; never commit to `main`). Commit prefix `claude:`.
- **Spec:** `docs/superpowers/specs/2026-06-24-phase2a-backend-design.md`.

---

## File Structure

```
app/
  __init__.py            # create_app() factory: config, sessions, blueprints, get_db, error handlers
  config.py              # APP_DATA_DIR resolution, db/auth paths, scrypt params
  crypto.py              # bcrypt verify + scrypt KEK + AES-GCM wrap/unwrap (pure primitives)
  account.py             # account lifecycle: exists / create / authenticate / change_password (auth.json I/O)
  storage.py             # SQLCipher connect (PRAGMA key) + schema init
  audit.py               # write_audit(conn, username, event_type, detail)
  validation.py          # per-row CDR validation (reuses phase1 loader constants)
  auth.py                # blueprint: /setup /login /logout /change-password + login_required
  imports.py             # blueprint: /imports (xlsx) + /datasets list/detail/delete
  targets.py             # blueprint: /targets CRUD
  detection_bridge.py    # ONLY seam to phase1_cdr: rows -> DataFrame -> detectors -> JSON
  analysis.py            # blueprint: /targets/<id>/analyze + /result
main.py                  # entry point: Flask thread + PyWebView window
tests/phase2a/
  conftest.py            # fixtures: temp APP_DATA_DIR, app/client, sample .xlsx from Phase 1 CSV
  test_crypto.py
  test_storage.py
  test_account.py
  test_auth.py
  test_imports.py
  test_targets.py
  test_analysis.py
  test_audit.py
  test_phase1_regression.py
requirements.txt         # extended
.gitignore               # add app-data + data/
```

Note vs spec §2: the spec listed `auth.py` as owning setup/authenticate logic. This plan splits the non-HTTP account lifecycle into `account.py` so the `auth.py` blueprint stays HTTP-only (clearer boundaries, easier to unit-test the crypto path without a request). This is the only structural refinement; all spec behavior is unchanged.

---

## Task 1: Dependencies, config, gitignore

**Files:**
- Modify: `requirements.txt`
- Modify: `.gitignore`
- Create: `app/__init__.py` (empty package marker for now)
- Create: `app/config.py`
- Test: `tests/phase2a/test_config.py`, `tests/phase2a/conftest.py`

**Interfaces:**
- Produces: `app.config.app_data_dir() -> pathlib.Path`, `app.config.db_path() -> Path`, `app.config.auth_path() -> Path`, and `app.config.SCRYPT_N`, `SCRYPT_R`, `SCRYPT_P`, `SCRYPT_LEN`, `SCRYPT_SALT_BYTES` constants. All path functions read the `APP_DATA_DIR` env var fresh on each call and create the directory if missing.

- [ ] **Step 1: Add dependencies**

Append to `requirements.txt` (keep existing `pandas`, `openpyxl`, `pytest`):

```
flask
pywebview
bcrypt
cryptography
sqlcipher3-wheels
```

- [ ] **Step 2: Install and verify SQLCipher imports on this machine**

Run:
```bash
cd "C:/Users/nadim/OneDrive/Desktop/la passion"
pip install -r requirements.txt
python -c "from sqlcipher3 import dbapi2 as sq; print('sqlcipher ok', sq.sqlite_version)"
python -c "import flask, webview, bcrypt; from cryptography.hazmat.primitives.kdf.scrypt import Scrypt; print('deps ok')"
```
Expected: prints `sqlcipher ok <version>` and `deps ok` with no ImportError. (If `webview` import fails on a headless CI, that is acceptable — PyWebView is only needed by `main.py`, not the API tests; note it and continue.)

- [ ] **Step 3: Update .gitignore**

Append to `.gitignore`:

```
# Phase 2A app-data (encrypted DB + auth sidecar) — never committed
data/
*.db
auth.json
```

- [ ] **Step 4: Write the failing test**

Create `tests/phase2a/conftest.py`:

```python
import os
import pathlib
import pytest


@pytest.fixture()
def app_data_dir(tmp_path, monkeypatch):
    """Point all app-data at an isolated temp dir for every test."""
    d = tmp_path / "appdata"
    monkeypatch.setenv("APP_DATA_DIR", str(d))
    return pathlib.Path(d)
```

Create `tests/phase2a/test_config.py`:

```python
from app import config


def test_app_data_dir_uses_env_and_is_created(app_data_dir):
    resolved = config.app_data_dir()
    assert resolved == app_data_dir
    assert resolved.is_dir()


def test_db_and_auth_paths_live_in_app_data_dir(app_data_dir):
    assert config.db_path() == app_data_dir / "cdr.db"
    assert config.auth_path() == app_data_dir / "auth.json"
```

- [ ] **Step 5: Run test to verify it fails**

Run: `pytest tests/phase2a/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.config'` (or AttributeError).

- [ ] **Step 6: Implement config.py**

Create `app/config.py`:

```python
"""Filesystem locations and crypto tunables for the Phase 2A backend.

No secrets live here. The encrypted DB and the (non-secret) auth.json sidecar
live under APP_DATA_DIR, which defaults to %LOCALAPPDATA%\\LaPassionCDR on
Windows and ~/.lapassioncdr elsewhere, and is overridable via the APP_DATA_DIR
environment variable (tests point it at a temp dir).
"""

from __future__ import annotations

import os
import pathlib

# scrypt parameters for deriving the key-encryption-key from the password.
SCRYPT_N = 2 ** 14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_LEN = 32          # 256-bit KEK
SCRYPT_SALT_BYTES = 16
DB_KEY_BYTES = 32        # 256-bit SQLCipher key
GCM_NONCE_BYTES = 12


def app_data_dir() -> pathlib.Path:
    """Return the app-data directory, creating it if needed."""
    override = os.environ.get("APP_DATA_DIR")
    if override:
        base = pathlib.Path(override)
    elif os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        base = pathlib.Path(os.environ["LOCALAPPDATA"]) / "LaPassionCDR"
    else:
        base = pathlib.Path.home() / ".lapassioncdr"
    base.mkdir(parents=True, exist_ok=True)
    return base


def db_path() -> pathlib.Path:
    return app_data_dir() / "cdr.db"


def auth_path() -> pathlib.Path:
    return app_data_dir() / "auth.json"
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/phase2a/test_config.py -v`
Expected: 2 passed.

- [ ] **Step 8: Commit**

```bash
git add requirements.txt .gitignore app/__init__.py app/config.py tests/phase2a/conftest.py tests/phase2a/test_config.py
git commit -m "claude: phase2a task 1 - deps, config, app-data paths"
```

---

## Task 2: Crypto primitives (`crypto.py`)

**Files:**
- Create: `app/crypto.py`
- Test: `tests/phase2a/test_crypto.py`

**Interfaces:**
- Produces:
  - `hash_password(password: str) -> str` (bcrypt hash, utf-8 str)
  - `verify_password(password: str, hashed: str) -> bool`
  - `derive_kek(password: str, salt: bytes) -> bytes` (32 bytes, scrypt)
  - `wrap_key(kek: bytes, db_key: bytes) -> tuple[bytes, bytes]` returns `(nonce, ciphertext)`
  - `unwrap_key(kek: bytes, nonce: bytes, ciphertext: bytes) -> bytes` raises `cryptography.exceptions.InvalidTag` on a wrong KEK.

- [ ] **Step 1: Write the failing test**

Create `tests/phase2a/test_crypto.py`:

```python
import os
import pytest
from cryptography.exceptions import InvalidTag
from app import crypto


def test_bcrypt_roundtrip():
    h = crypto.hash_password("hunter2")
    assert h != "hunter2"
    assert crypto.verify_password("hunter2", h) is True
    assert crypto.verify_password("wrong", h) is False


def test_envelope_roundtrip_recovers_db_key():
    salt = os.urandom(16)
    db_key = os.urandom(32)
    kek = crypto.derive_kek("hunter2", salt)
    nonce, ct = crypto.wrap_key(kek, db_key)
    assert crypto.unwrap_key(kek, nonce, ct) == db_key


def test_wrong_password_cannot_unwrap():
    salt = os.urandom(16)
    db_key = os.urandom(32)
    good = crypto.derive_kek("hunter2", salt)
    bad = crypto.derive_kek("WRONG", salt)
    nonce, ct = crypto.wrap_key(good, db_key)
    with pytest.raises(InvalidTag):
        crypto.unwrap_key(bad, nonce, ct)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/phase2a/test_crypto.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.crypto'`.

- [ ] **Step 3: Implement crypto.py**

Create `app/crypto.py`:

```python
"""Cryptographic primitives for single-account auth and envelope key-wrapping.

Two distinct jobs, two functions:
  * bcrypt  -> the password *verifier* (the requirement names bcrypt).
  * scrypt  -> derives the key-encryption-key (KEK) used to AES-GCM-wrap the
               random 256-bit SQLCipher database key.
The raw database key is never written to disk; only its wrapped form is.
"""

from __future__ import annotations

import bcrypt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from app import config


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def derive_kek(password: str, salt: bytes) -> bytes:
    kdf = Scrypt(
        salt=salt,
        length=config.SCRYPT_LEN,
        n=config.SCRYPT_N,
        r=config.SCRYPT_R,
        p=config.SCRYPT_P,
    )
    return kdf.derive(password.encode("utf-8"))


def wrap_key(kek: bytes, db_key: bytes) -> tuple[bytes, bytes]:
    import os

    nonce = os.urandom(config.GCM_NONCE_BYTES)
    ciphertext = AESGCM(kek).encrypt(nonce, db_key, None)
    return nonce, ciphertext


def unwrap_key(kek: bytes, nonce: bytes, ciphertext: bytes) -> bytes:
    # Raises cryptography.exceptions.InvalidTag if the KEK is wrong.
    return AESGCM(kek).decrypt(nonce, ciphertext, None)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/phase2a/test_crypto.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add app/crypto.py tests/phase2a/test_crypto.py
git commit -m "claude: phase2a task 2 - crypto primitives (bcrypt, scrypt KEK, AES-GCM wrap)"
```

---

## Task 3: SQLCipher storage + schema + on-disk encryption proof (`storage.py`)

**Files:**
- Create: `app/storage.py`
- Test: `tests/phase2a/test_storage.py`

**Interfaces:**
- Produces:
  - `connect(db_key: bytes) -> sqlcipher3.dbapi2.Connection` — opens `config.db_path()`, applies `PRAGMA key` (raw hex blob) and `PRAGMA foreign_keys = ON`, sets `row_factory` to `sqlite3.Row`-like access.
  - `init_schema(conn) -> None` — creates all five tables + index (idempotent via `IF NOT EXISTS`).
  - `SCHEMA_SQL: str` — the DDL.

- [ ] **Step 1: Write the failing test**

Create `tests/phase2a/test_storage.py`:

```python
import os
import sqlite3
import pytest
from app import storage, config


def test_schema_creates_all_tables(app_data_dir):
    key = os.urandom(32)
    conn = storage.connect(key)
    storage.init_schema(conn)
    names = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {"datasets", "cdr_records", "targets", "analysis_results", "audit_log"} <= names
    conn.close()


def test_db_file_is_encrypted_on_disk(app_data_dir):
    key = os.urandom(32)
    conn = storage.connect(key)
    storage.init_schema(conn)
    conn.close()

    raw = config.db_path().read_bytes()
    # A plaintext SQLite file begins with this magic string; an encrypted one must not.
    assert not raw.startswith(b"SQLite format 3\x00")

    # Plain sqlite3 (no key) cannot read an encrypted DB.
    with pytest.raises(sqlite3.DatabaseError):
        bad = sqlite3.connect(config.db_path())
        bad.execute("SELECT name FROM sqlite_master").fetchall()


def test_foreign_keys_enforced(app_data_dir):
    key = os.urandom(32)
    conn = storage.connect(key)
    storage.init_schema(conn)
    with pytest.raises(Exception):
        conn.execute(
            "INSERT INTO targets (name, dataset_id, phone_number, created_at) "
            "VALUES (?, ?, ?, ?)",
            ("x", 999, "01000001", "2026-01-01T00:00:00+00:00"),
        )
        conn.commit()
    conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/phase2a/test_storage.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.storage'`.

- [ ] **Step 3: Implement storage.py**

Create `app/storage.py`:

```python
"""SQLCipher-backed storage: encrypted connection + schema.

The database key is the raw 32-byte value produced at setup (see account.py).
It is passed to SQLCipher as a hex blob via `PRAGMA key`, which must run before
any other statement on the connection.
"""

from __future__ import annotations

from sqlcipher3 import dbapi2 as sqlcipher

from app import config

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS datasets (
  id            INTEGER PRIMARY KEY,
  name          TEXT NOT NULL,
  filename      TEXT NOT NULL,
  imported_at   TEXT NOT NULL,
  row_count     INTEGER NOT NULL,
  skipped_count INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS cdr_records (
  id               INTEGER PRIMARY KEY,
  dataset_id       INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
  phone_number     TEXT NOT NULL,
  imei             TEXT,
  area             TEXT NOT NULL,
  timestamp        TEXT NOT NULL,
  call_type        INTEGER NOT NULL,
  duration_seconds INTEGER NOT NULL,
  other_party      TEXT,
  other_imei       TEXT,
  other_area       TEXT
);

CREATE INDEX IF NOT EXISTS idx_records_dataset_phone
  ON cdr_records(dataset_id, phone_number);

CREATE TABLE IF NOT EXISTS targets (
  id           INTEGER PRIMARY KEY,
  name         TEXT NOT NULL,
  dataset_id   INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
  phone_number TEXT NOT NULL,
  created_at   TEXT NOT NULL,
  UNIQUE(dataset_id, phone_number)
);

CREATE TABLE IF NOT EXISTS analysis_results (
  id          INTEGER PRIMARY KEY,
  target_id   INTEGER NOT NULL REFERENCES targets(id) ON DELETE CASCADE,
  created_at  TEXT NOT NULL,
  result_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
  id         INTEGER PRIMARY KEY,
  ts         TEXT NOT NULL,
  username   TEXT NOT NULL,
  event_type TEXT NOT NULL,
  detail     TEXT
);
"""


def connect(db_key: bytes):
    conn = sqlcipher.connect(str(config.db_path()))
    conn.row_factory = sqlcipher.Row
    # PRAGMA key MUST be the first statement. Raw key as a hex blob (x'..').
    conn.execute(f"PRAGMA key = \"x'{db_key.hex()}'\"")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/phase2a/test_storage.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add app/storage.py tests/phase2a/test_storage.py
git commit -m "claude: phase2a task 3 - SQLCipher storage, schema, on-disk encryption proof"
```

---

## Task 4: Account lifecycle (`account.py`)

**Files:**
- Create: `app/account.py`
- Test: `tests/phase2a/test_account.py`

**Interfaces:**
- Consumes: `crypto.*`, `storage.connect/init_schema`, `config.auth_path/db_path`.
- Produces:
  - `account_exists() -> bool` (auth.json present)
  - `create_account(username: str, password: str) -> bytes` — writes auth.json, creates encrypted DB + schema, returns the raw `db_key`. Raises `AccountExistsError` if one exists.
  - `authenticate(username: str, password: str) -> bytes` — returns the raw `db_key`. Raises `AuthError` on bad username/password.
  - `change_password(old_password: str, new_password: str) -> None` — re-wraps the same db_key under a new KEK + salt; updates bcrypt hash. Raises `AuthError` if `old_password` wrong.
  - Exceptions `AccountExistsError`, `AuthError`.

- [ ] **Step 1: Write the failing test**

Create `tests/phase2a/test_account.py`:

```python
import pytest
from app import account, storage


def test_setup_creates_account_and_encrypted_db(app_data_dir):
    assert account.account_exists() is False
    db_key = account.create_account("nadim", "hunter2")
    assert account.account_exists() is True
    assert isinstance(db_key, bytes) and len(db_key) == 32
    # The returned key opens the DB and the schema is present.
    conn = storage.connect(db_key)
    names = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "datasets" in names
    conn.close()


def test_second_setup_raises(app_data_dir):
    account.create_account("nadim", "hunter2")
    with pytest.raises(account.AccountExistsError):
        account.create_account("other", "x")


def test_authenticate_returns_same_key(app_data_dir):
    created = account.create_account("nadim", "hunter2")
    got = account.authenticate("nadim", "hunter2")
    assert got == created


def test_authenticate_rejects_bad_password_and_user(app_data_dir):
    account.create_account("nadim", "hunter2")
    with pytest.raises(account.AuthError):
        account.authenticate("nadim", "WRONG")
    with pytest.raises(account.AuthError):
        account.authenticate("someoneelse", "hunter2")


def test_change_password_preserves_db_key(app_data_dir):
    original = account.create_account("nadim", "hunter2")
    account.change_password("hunter2", "newpass9")
    with pytest.raises(account.AuthError):
        account.authenticate("nadim", "hunter2")
    assert account.authenticate("nadim", "newpass9") == original


def test_change_password_wrong_old_raises(app_data_dir):
    account.create_account("nadim", "hunter2")
    with pytest.raises(account.AuthError):
        account.change_password("WRONG", "newpass9")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/phase2a/test_account.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.account'`.

- [ ] **Step 3: Implement account.py**

Create `app/account.py`:

```python
"""Single-account lifecycle: setup, authenticate, change-password.

Stores only non-secret material in the auth.json sidecar:
  { username, bcrypt_hash, kdf_salt, db_key_nonce, wrapped_db_key, created_at }
All binary fields are base64-encoded. The raw db_key is returned in-memory to
the caller (the Flask app holds it for the session) but never written to disk.
"""

from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timezone

from cryptography.exceptions import InvalidTag

from app import config, crypto, storage


class AccountExistsError(Exception):
    pass


class AuthError(Exception):
    pass


def _b64e(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _b64d(s: str) -> bytes:
    return base64.b64decode(s.encode("ascii"))


def account_exists() -> bool:
    return config.auth_path().exists()


def _load() -> dict:
    with open(config.auth_path(), "r", encoding="utf-8") as fh:
        return json.load(fh)


def _save(record: dict) -> None:
    with open(config.auth_path(), "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2)
        fh.write("\n")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_account(username: str, password: str) -> bytes:
    if account_exists():
        raise AccountExistsError("an account already exists")
    salt = os.urandom(config.SCRYPT_SALT_BYTES)
    db_key = os.urandom(config.DB_KEY_BYTES)
    kek = crypto.derive_kek(password, salt)
    nonce, wrapped = crypto.wrap_key(kek, db_key)
    _save({
        "username": username,
        "bcrypt_hash": crypto.hash_password(password),
        "kdf_salt": _b64e(salt),
        "db_key_nonce": _b64e(nonce),
        "wrapped_db_key": _b64e(wrapped),
        "created_at": _now(),
    })
    conn = storage.connect(db_key)
    storage.init_schema(conn)
    conn.close()
    return db_key


def authenticate(username: str, password: str) -> bytes:
    if not account_exists():
        raise AuthError("no account")
    rec = _load()
    if username != rec["username"] or not crypto.verify_password(password, rec["bcrypt_hash"]):
        raise AuthError("bad credentials")
    kek = crypto.derive_kek(password, _b64d(rec["kdf_salt"]))
    try:
        return crypto.unwrap_key(kek, _b64d(rec["db_key_nonce"]), _b64d(rec["wrapped_db_key"]))
    except InvalidTag as exc:  # pragma: no cover - defence in depth
        raise AuthError("bad credentials") from exc


def change_password(old_password: str, new_password: str) -> None:
    rec = _load()
    db_key = authenticate(rec["username"], old_password)  # raises AuthError if wrong
    salt = os.urandom(config.SCRYPT_SALT_BYTES)
    kek = crypto.derive_kek(new_password, salt)
    nonce, wrapped = crypto.wrap_key(kek, db_key)
    rec.update({
        "bcrypt_hash": crypto.hash_password(new_password),
        "kdf_salt": _b64e(salt),
        "db_key_nonce": _b64e(nonce),
        "wrapped_db_key": _b64e(wrapped),
    })
    _save(rec)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/phase2a/test_account.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add app/account.py tests/phase2a/test_account.py
git commit -m "claude: phase2a task 4 - account lifecycle (setup/authenticate/change-password)"
```

---

## Task 5: Audit log writer (`audit.py`)

**Files:**
- Create: `app/audit.py`
- Test: `tests/phase2a/test_audit.py`

**Interfaces:**
- Produces: `write_audit(conn, username: str, event_type: str, detail: dict | None = None) -> None` — inserts one row with a UTC ISO timestamp; `detail` is JSON-encoded (or NULL). Also exposes the event-type string constants.

- [ ] **Step 1: Write the failing test**

Create `tests/phase2a/test_audit.py`:

```python
import os
from app import storage, audit


def test_write_audit_inserts_row_with_timestamp(app_data_dir):
    key = os.urandom(32)
    conn = storage.connect(key)
    storage.init_schema(conn)
    audit.write_audit(conn, "nadim", audit.LOGIN_SUCCESS, {"foo": "bar"})
    conn.commit()
    row = conn.execute(
        "SELECT username, event_type, detail, ts FROM audit_log").fetchone()
    assert row["username"] == "nadim"
    assert row["event_type"] == "LOGIN_SUCCESS"
    assert "foo" in row["detail"]
    assert row["ts"]  # non-empty ISO timestamp
    conn.close()


def test_write_audit_allows_null_detail(app_data_dir):
    key = os.urandom(32)
    conn = storage.connect(key)
    storage.init_schema(conn)
    audit.write_audit(conn, "nadim", audit.LOGOUT)
    conn.commit()
    row = conn.execute("SELECT detail FROM audit_log").fetchone()
    assert row["detail"] is None
    conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/phase2a/test_audit.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.audit'`.

- [ ] **Step 3: Implement audit.py**

Create `app/audit.py`:

```python
"""Audit-log writer. Never logs passwords or keys."""

from __future__ import annotations

import json
from datetime import datetime, timezone

SETUP = "SETUP"
LOGIN_SUCCESS = "LOGIN_SUCCESS"
LOGIN_FAIL = "LOGIN_FAIL"
LOGOUT = "LOGOUT"
IMPORT = "IMPORT"
TARGET_CREATE = "TARGET_CREATE"
TARGET_DELETE = "TARGET_DELETE"
ANALYSIS = "ANALYSIS"
CHANGE_PASSWORD = "CHANGE_PASSWORD"


def write_audit(conn, username: str, event_type: str, detail: dict | None = None) -> None:
    conn.execute(
        "INSERT INTO audit_log (ts, username, event_type, detail) VALUES (?, ?, ?, ?)",
        (
            datetime.now(timezone.utc).isoformat(),
            username,
            event_type,
            json.dumps(detail) if detail is not None else None,
        ),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/phase2a/test_audit.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add app/audit.py tests/phase2a/test_audit.py
git commit -m "claude: phase2a task 5 - audit log writer"
```

---

## Task 6: App factory, sessions, public routes, get_db, error envelope (`__init__.py`)

**Files:**
- Modify: `app/__init__.py`
- Test: `tests/phase2a/test_app.py`

**Interfaces:**
- Consumes: `account.account_exists`, `config`.
- Produces:
  - `create_app() -> flask.Flask` with: `SECRET_KEY=os.urandom(32)`, session cookie `HttpOnly` + `SameSite=Strict`, a per-request `get_db()` helper using `app.config["DB_KEY"]`, `login_required` decorator, JSON error handlers, and the public routes `GET /api/health`, `GET /api/status`.
  - Module-level helpers used by blueprints: `from app import get_db, login_required, ok, err`.
  - `ok(data, status=200)` and `err(code, message, status)` return Flask JSON responses in the `{"ok": ...}` envelope.
- The unlocked state lives in `app.config["DB_KEY"]` (bytes or None) and `app.config["USERNAME"]`. `get_db()` opens a fresh SQLCipher connection per request from that key, caches it on `flask.g`, and closes it on teardown (thread-safe — no shared connection).

- [ ] **Step 1: Write the failing test**

Create `tests/phase2a/test_app.py`:

```python
import pytest
from app import create_app


@pytest.fixture()
def client(app_data_dir):
    app = create_app()
    app.config.update(TESTING=True)
    return app.test_client()


def test_health_is_public(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.get_json()["data"]["status"] == "ok"


def test_status_reports_no_account_initially(client):
    r = client.get("/api/status")
    body = r.get_json()
    assert body["data"]["account_exists"] is False
    assert body["data"]["authenticated"] is False


def test_unknown_route_returns_json_envelope(client):
    r = client.get("/api/does-not-exist")
    assert r.status_code == 404
    assert r.get_json()["ok"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/phase2a/test_app.py -v`
Expected: FAIL — `create_app` not importable / not defined.

- [ ] **Step 3: Implement the app factory**

Replace `app/__init__.py` with:

```python
"""Flask application factory for the Phase 2A backend."""

from __future__ import annotations

import functools
import os

from flask import Flask, g, jsonify, request, session

from app import account, config, storage


def ok(data=None, status: int = 200):
    return jsonify({"ok": True, "data": data}), status


def err(code: str, message: str, status: int):
    return jsonify({"ok": False, "error": {"code": code, "message": message}}), status


def get_db():
    """A per-request SQLCipher connection opened from the in-memory db_key."""
    from flask import current_app

    if "db" not in g:
        key = current_app.config.get("DB_KEY")
        if key is None:
            raise RuntimeError("no database key in session")
        g.db = storage.connect(key)
    return g.db


def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        from flask import current_app

        if not session.get("authenticated") or current_app.config.get("DB_KEY") is None:
            return err("UNAUTHENTICATED", "login required", 401)
        # Reject non-JSON bodies on state-changing requests (light CSRF hardening).
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.content_length:
            if not request.is_json and "multipart/form-data" not in (request.content_type or ""):
                return err("BAD_CONTENT_TYPE", "JSON required", 415)
        return view(*args, **kwargs)

    return wrapped


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.urandom(32),          # per-launch; no hardcoded secret
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        DB_KEY=None,
        USERNAME=None,
    )

    @app.teardown_appcontext
    def _close_db(exc):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    @app.get("/api/health")
    def health():
        return ok({"status": "ok"})

    @app.get("/api/status")
    def status():
        return ok({
            "account_exists": account.account_exists(),
            "authenticated": bool(session.get("authenticated")),
        })

    @app.errorhandler(404)
    def _404(e):
        return err("NOT_FOUND", "resource not found", 404)

    @app.errorhandler(405)
    def _405(e):
        return err("METHOD_NOT_ALLOWED", "method not allowed", 405)

    @app.errorhandler(500)
    def _500(e):  # pragma: no cover
        return err("INTERNAL", "internal error", 500)

    # Blueprints registered in later tasks:
    from app.auth import bp as auth_bp
    app.register_blueprint(auth_bp)
    from app.imports import bp as imports_bp
    app.register_blueprint(imports_bp)
    from app.targets import bp as targets_bp
    app.register_blueprint(targets_bp)
    from app.analysis import bp as analysis_bp
    app.register_blueprint(analysis_bp)

    return app
```

NOTE for the implementer: the four blueprint imports at the bottom will fail until Tasks 7–11 create those modules. To keep this task independently green, **temporarily comment out the four `register_blueprint` blocks**, get this task's tests passing and committed, then uncomment each as its task lands. Each later task's test run will re-exercise the factory.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/phase2a/test_app.py -v`
Expected: 3 passed (with blueprint registrations commented out).

- [ ] **Step 5: Commit**

```bash
git add app/__init__.py tests/phase2a/test_app.py
git commit -m "claude: phase2a task 6 - app factory, sessions, health/status, get_db, error envelope"
```

---

## Task 7: Auth blueprint — setup, login, logout, change-password (`auth.py`)

**Files:**
- Create: `app/auth.py`
- Modify: `app/__init__.py` (uncomment the `auth_bp` registration)
- Test: `tests/phase2a/test_auth.py`

**Interfaces:**
- Consumes: `account.*`, `app.ok/err/login_required/get_db`, `audit.*`.
- Produces: blueprint `bp` with `POST /api/setup`, `POST /api/login`, `POST /api/logout`, `POST /api/change-password`. On setup/login it sets `current_app.config["DB_KEY"]`/`["USERNAME"]` and `session["authenticated"]=True`; logout clears them.

- [ ] **Step 1: Write the failing test**

Create `tests/phase2a/test_auth.py`:

```python
import pytest
from app import create_app


@pytest.fixture()
def client(app_data_dir):
    app = create_app()
    app.config.update(TESTING=True)
    return app.test_client()


def _setup(client, u="nadim", p="hunter2"):
    return client.post("/api/setup", json={"username": u, "password": p})


def test_setup_then_second_setup_conflicts(client):
    assert _setup(client).status_code == 201
    assert _setup(client).status_code == 409


def test_protected_route_requires_login(client):
    _setup(client)
    client.post("/api/logout")
    r = client.get("/api/targets")
    assert r.status_code == 401


def test_login_good_and_bad(client):
    _setup(client)
    client.post("/api/logout")
    assert client.post("/api/login", json={"username": "nadim", "password": "hunter2"}).status_code == 200
    client.post("/api/logout")
    assert client.post("/api/login", json={"username": "nadim", "password": "no"}).status_code == 401


def test_change_password_flow(client):
    _setup(client)
    assert client.post("/api/change-password",
                       json={"old_password": "WRONG", "new_password": "newpass9"}).status_code == 401
    assert client.post("/api/change-password",
                       json={"old_password": "hunter2", "new_password": "newpass9"}).status_code == 200
    client.post("/api/logout")
    assert client.post("/api/login", json={"username": "nadim", "password": "newpass9"}).status_code == 200


def test_login_failure_is_audited(client):
    _setup(client)
    client.post("/api/logout")
    client.post("/api/login", json={"username": "nadim", "password": "no"})
    # Re-login to read the audit log through an authed connection.
    client.post("/api/login", json={"username": "nadim", "password": "hunter2"})
    from app import storage, account
    key = account.authenticate("nadim", "hunter2")
    conn = storage.connect(key)
    events = [r["event_type"] for r in conn.execute("SELECT event_type FROM audit_log").fetchall()]
    assert "LOGIN_FAIL" in events
    assert "SETUP" in events
    conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/phase2a/test_auth.py -v`
Expected: FAIL — `app.auth` not importable.

- [ ] **Step 3: Implement auth.py**

Create `app/auth.py`:

```python
"""Auth blueprint: setup / login / logout / change-password."""

from __future__ import annotations

from flask import Blueprint, current_app, request, session

from app import account, audit, err, get_db, login_required, ok, storage

bp = Blueprint("auth", __name__, url_prefix="/api")


def _unlock(username: str, db_key: bytes) -> None:
    current_app.config["DB_KEY"] = db_key
    current_app.config["USERNAME"] = username
    session["authenticated"] = True


def _audit(username: str, event: str, detail=None) -> None:
    """Write an audit row using the currently-unlocked connection."""
    db = get_db()
    audit.write_audit(db, username, event, detail)
    db.commit()


@bp.post("/setup")
def setup():
    body = request.get_json(silent=True) or {}
    username, password = body.get("username"), body.get("password")
    if not username or not password:
        return err("BAD_REQUEST", "username and password required", 400)
    try:
        db_key = account.create_account(username, password)
    except account.AccountExistsError:
        return err("ACCOUNT_EXISTS", "an account already exists", 409)
    _unlock(username, db_key)
    _audit(username, audit.SETUP)
    return ok({"username": username}, status=201)


@bp.post("/login")
def login():
    body = request.get_json(silent=True) or {}
    username, password = body.get("username"), body.get("password")
    if not username or not password:
        return err("BAD_REQUEST", "username and password required", 400)
    try:
        db_key = account.authenticate(username, password)
    except account.AuthError:
        # Audit the failed attempt with a short-lived connection if possible.
        try:
            rec_user = account._load().get("username", username) if account.account_exists() else username
            real_key = None
        except Exception:
            rec_user = username
        # Best-effort: open with a freshly-authenticated key is impossible here,
        # so record the failure on next successful unlock is not desired; instead
        # write via a transient connection using the stored account if unlocked.
        if current_app.config.get("DB_KEY") is not None:
            _audit(rec_user, audit.LOGIN_FAIL, {"username": username})
        return err("UNAUTHENTICATED", "bad credentials", 401)
    _unlock(username, db_key)
    _audit(username, audit.LOGIN_SUCCESS)
    return ok({"username": username})


@bp.post("/logout")
@login_required
def logout():
    username = current_app.config.get("USERNAME")
    _audit(username, audit.LOGOUT)
    current_app.config["DB_KEY"] = None
    current_app.config["USERNAME"] = None
    session.clear()
    return ok({})


@bp.post("/change-password")
@login_required
def change_password():
    body = request.get_json(silent=True) or {}
    old, new = body.get("old_password"), body.get("new_password")
    if not old or not new:
        return err("BAD_REQUEST", "old_password and new_password required", 400)
    try:
        account.change_password(old, new)
    except account.AuthError:
        return err("UNAUTHENTICATED", "old password incorrect", 401)
    username = current_app.config.get("USERNAME")
    _audit(username, audit.CHANGE_PASSWORD)
    return ok({})
```

IMPLEMENTER NOTE on `LOGIN_FAIL` auditing: a failed login has no db_key, so it cannot open the encrypted DB to write an audit row. The reliable way to record failed attempts is to write them on the **next successful unlock**, or to authenticate with the stored credentials internally. To keep this simple and correct, change the login handler to record `LOGIN_FAIL` like this instead of the best-effort block above — replace the `except account.AuthError:` body with:

```python
    except account.AuthError:
        # Record the failure by unlocking with the stored account is not possible
        # without the password. Buffer it: open the DB only if we can derive the
        # key from a subsequent success. Simplest correct approach: stash failed
        # attempts in app.config and flush them on the next successful login.
        fails = current_app.config.setdefault("PENDING_FAILS", [])
        fails.append({"username": username})
        return err("UNAUTHENTICATED", "bad credentials", 401)
```

and in the success path, right after `_unlock(...)` and before `_audit(username, audit.LOGIN_SUCCESS)`, flush them:

```python
    for f in current_app.config.pop("PENDING_FAILS", []):
        _audit(f["username"], audit.LOGIN_FAIL, f)
```

Use this buffered approach; it makes `test_login_failure_is_audited` pass deterministically. Remove the best-effort block.

- [ ] **Step 4: Uncomment the auth blueprint registration**

In `app/__init__.py`, ensure these two lines are active (not commented):

```python
    from app.auth import bp as auth_bp
    app.register_blueprint(auth_bp)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/phase2a/test_auth.py tests/phase2a/test_app.py -v`
Expected: all passed.

- [ ] **Step 6: Commit**

```bash
git add app/auth.py app/__init__.py tests/phase2a/test_auth.py
git commit -m "claude: phase2a task 7 - auth blueprint (setup/login/logout/change-password) + audit"
```

---

## Task 8: CDR row validation (`validation.py`)

**Files:**
- Create: `app/validation.py`
- Test: `tests/phase2a/test_validation.py`

**Interfaces:**
- Consumes (read-only) from Phase 1: `phase1_cdr.loader.REQUIRED_COLUMNS`, `phase1_cdr.loader.VALID_CALL_TYPES`. (Import via `sys.path` shim — see Step 3.)
- Produces:
  - `missing_columns(columns: list[str]) -> list[str]`
  - `validate_row(row: dict) -> tuple[dict | None, str | None]` — returns `(clean_row, None)` for a valid row (with parsed/normalized values) or `(None, reason)` for a skip. Checks: required non-empty (`phone_number`, `area`); parseable `timestamp` (ISO out); `call_type` ∈ VALID set; `duration_seconds` is a non-negative integer.

- [ ] **Step 1: Write the failing test**

Create `tests/phase2a/test_validation.py`:

```python
from app import validation


def test_missing_columns_detected():
    cols = ["phone_number", "imei", "area", "timestamp", "call_type"]  # missing 4
    missing = validation.missing_columns(cols)
    assert "duration_seconds" in missing
    assert "other_party" in missing


def test_valid_row_passes_and_normalizes_timestamp():
    row = {
        "phone_number": "01000001", "imei": "350", "area": "Hamra",
        "timestamp": "2024-01-01 03:15:00", "call_type": "1",
        "duration_seconds": "42", "other_party": "03200101",
        "other_imei": "350", "other_area": "Hamra",
    }
    clean, reason = validation.validate_row(row)
    assert reason is None
    assert clean["call_type"] == 1
    assert clean["duration_seconds"] == 42
    assert clean["timestamp"].startswith("2024-01-01T03:15:00")


def test_bad_call_type_skipped():
    row = {"phone_number": "x", "area": "Hamra", "timestamp": "2024-01-01 03:00:00",
           "call_type": "7", "duration_seconds": "5"}
    clean, reason = validation.validate_row(row)
    assert clean is None and "call_type" in reason


def test_unparseable_timestamp_skipped():
    row = {"phone_number": "x", "area": "Hamra", "timestamp": "not-a-date",
           "call_type": "1", "duration_seconds": "5"}
    clean, reason = validation.validate_row(row)
    assert clean is None and "timestamp" in reason


def test_negative_duration_skipped():
    row = {"phone_number": "x", "area": "Hamra", "timestamp": "2024-01-01 03:00:00",
           "call_type": "1", "duration_seconds": "-3"}
    clean, reason = validation.validate_row(row)
    assert clean is None and "duration" in reason
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/phase2a/test_validation.py -v`
Expected: FAIL — `app.validation` not importable.

- [ ] **Step 3: Implement validation.py**

Create `app/validation.py`:

```python
"""Per-row CDR validation for the import pipeline.

Reuses Phase 1's REQUIRED_COLUMNS / VALID_CALL_TYPES so import rules can never
drift from the algorithm. Phase 1 is imported read-only; nothing there is edited.
"""

from __future__ import annotations

import os
import sys

import pandas as pd

# Make the frozen phase1_cdr package importable without modifying it.
_PHASE1 = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "phase1_cdr")
if _PHASE1 not in sys.path:
    sys.path.insert(0, _PHASE1)

from loader import REQUIRED_COLUMNS, VALID_CALL_TYPES  # noqa: E402

# Values that may be empty (Phase 1 treats these as optional).
_REQUIRED_NONEMPTY = ("phone_number", "area")


def missing_columns(columns) -> list[str]:
    present = set(columns)
    return [c for c in REQUIRED_COLUMNS if c not in present]


def validate_row(row: dict):
    for field in _REQUIRED_NONEMPTY:
        value = row.get(field)
        if value is None or str(value).strip() == "":
            return None, f"{field} is required"

    ts = pd.to_datetime(row.get("timestamp"), errors="coerce")
    if pd.isna(ts):
        return None, "unparseable timestamp"

    try:
        call_type = int(float(row.get("call_type")))
    except (TypeError, ValueError):
        return None, "invalid call_type"
    if call_type not in VALID_CALL_TYPES:
        return None, f"call_type {call_type} not in {sorted(VALID_CALL_TYPES)}"

    try:
        duration = int(float(row.get("duration_seconds")))
    except (TypeError, ValueError):
        return None, "invalid duration_seconds"
    if duration < 0:
        return None, "negative duration_seconds"

    def _s(v):
        return None if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)

    clean = {
        "phone_number": str(row["phone_number"]),
        "imei": _s(row.get("imei")),
        "area": str(row["area"]),
        "timestamp": ts.isoformat(),
        "call_type": call_type,
        "duration_seconds": duration,
        "other_party": _s(row.get("other_party")),
        "other_imei": _s(row.get("other_imei")),
        "other_area": _s(row.get("other_area")),
    }
    return clean, None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/phase2a/test_validation.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add app/validation.py tests/phase2a/test_validation.py
git commit -m "claude: phase2a task 8 - CDR row validation (reuses phase1 loader constants)"
```

---

## Task 9: Import pipeline + datasets endpoints (`imports.py`)

**Files:**
- Create: `app/imports.py`
- Modify: `app/__init__.py` (uncomment `imports_bp` registration)
- Modify: `tests/phase2a/conftest.py` (add the `sample_xlsx` fixture from Phase 1 data)
- Test: `tests/phase2a/test_imports.py`

**Interfaces:**
- Consumes: `get_db`, `ok/err/login_required`, `validation.*`, `audit.*`, pandas/openpyxl.
- Produces: blueprint `bp` with `POST /api/imports` (multipart), `GET /api/datasets`, `GET /api/datasets/<int:dataset_id>/phone-numbers`, `DELETE /api/datasets/<int:dataset_id>`.

- [ ] **Step 1: Add the shared sample-xlsx fixture**

Append to `tests/phase2a/conftest.py`:

```python
import pandas as pd


@pytest.fixture()
def sample_xlsx(tmp_path):
    """Convert Phase 1's existing synthetic sample_data.csv (users A-E) to .xlsx.

    Reuses real Phase 1 fixture data - no invented rows. If the CSV is missing,
    regenerate it deterministically via Phase 1's dev_fixtures.
    """
    import subprocess
    import sys

    here = pathlib.Path(__file__).resolve().parents[2]
    csv = here / "phase1_cdr" / "sample_data.csv"
    if not csv.exists():
        subprocess.run([sys.executable, str(here / "phase1_cdr" / "dev_fixtures.py")],
                       check=True, cwd=str(here / "phase1_cdr"))
    df = pd.read_csv(csv, dtype={"phone_number": str, "imei": str,
                                 "other_party": str, "other_imei": str})
    out = tmp_path / "sample.xlsx"
    df.to_excel(out, index=False, engine="openpyxl")
    return out
```

- [ ] **Step 2: Write the failing test**

Create `tests/phase2a/test_imports.py`:

```python
import io
import pytest
import pandas as pd
from app import create_app


@pytest.fixture()
def client(app_data_dir):
    app = create_app()
    app.config.update(TESTING=True)
    c = app.test_client()
    c.post("/api/setup", json={"username": "nadim", "password": "hunter2"})
    return c


def _upload(client, path, name="dataset1"):
    with open(path, "rb") as fh:
        data = {"name": name, "file": (io.BytesIO(fh.read()), "sample.xlsx")}
    return client.post("/api/imports", data=data, content_type="multipart/form-data")


def test_valid_import_reports_counts(client, sample_xlsx):
    r = _upload(client, sample_xlsx)
    assert r.status_code == 201
    data = r.get_json()["data"]
    assert data["imported"] > 0
    assert data["skipped"] == 0
    # Phase 1 sample has 5 users; phone-numbers endpoint should list them.
    ds_id = data["dataset_id"]
    pn = client.get(f"/api/datasets/{ds_id}/phone-numbers").get_json()["data"]
    assert len(pn) == 5


def test_missing_column_rejected(client, tmp_path):
    bad = tmp_path / "bad.xlsx"
    pd.DataFrame({"phone_number": ["x"], "area": ["Hamra"]}).to_excel(bad, index=False)
    r = _upload(client, bad)
    assert r.status_code == 400
    assert r.get_json()["error"]["code"] == "SCHEMA_MISMATCH"


def test_bad_rows_are_skipped_with_reasons(client, sample_xlsx, tmp_path):
    df = pd.read_excel(sample_xlsx, dtype={"phone_number": str})
    df.loc[0, "call_type"] = 7          # invalid
    df.loc[1, "timestamp"] = "nope"     # unparseable
    df.loc[2, "duration_seconds"] = -5  # negative
    mixed = tmp_path / "mixed.xlsx"
    df.to_excel(mixed, index=False)
    r = _upload(client, mixed)
    data = r.get_json()["data"]
    assert data["skipped"] >= 3
    assert len(data["skipped_reasons"]) >= 3


def test_corrupt_file_does_not_crash(client, tmp_path):
    junk = tmp_path / "junk.xlsx"
    junk.write_bytes(b"this is not a real xlsx")
    r = _upload(client, junk)
    assert r.status_code == 400
    assert r.get_json()["error"]["code"] == "BAD_FILE"


def test_delete_dataset_cascades(client, sample_xlsx):
    ds_id = _upload(client, sample_xlsx).get_json()["data"]["dataset_id"]
    assert client.delete(f"/api/datasets/{ds_id}").status_code == 200
    assert client.get("/api/datasets").get_json()["data"] == []
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/phase2a/test_imports.py -v`
Expected: FAIL — `app.imports` not importable.

- [ ] **Step 4: Implement imports.py**

Create `app/imports.py`:

```python
"""Import pipeline (xlsx) + dataset listing/deletion."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
from flask import Blueprint, current_app, request

from app import audit, err, get_db, login_required, ok, validation

bp = Blueprint("imports", __name__, url_prefix="/api")


@bp.post("/imports")
@login_required
def import_xlsx():
    name = (request.form.get("name") or "").strip()
    if not name:
        return err("BAD_REQUEST", "a dataset name is required", 400)
    upload = request.files.get("file")
    if upload is None or upload.filename == "":
        return err("BAD_REQUEST", "a .xlsx file is required", 400)
    if not upload.filename.lower().endswith(".xlsx"):
        return err("BAD_FILE", "only .xlsx files are supported", 400)

    try:
        df = pd.read_excel(upload, dtype=str, engine="openpyxl")
    except Exception:
        return err("BAD_FILE", "file could not be read as .xlsx", 400)

    missing = validation.missing_columns(list(df.columns))
    if missing:
        return err("SCHEMA_MISMATCH", "missing columns: " + ", ".join(missing), 400)

    clean_rows, skipped_reasons = [], []
    for i, raw in enumerate(df.to_dict(orient="records")):
        clean, reason = validation.validate_row(raw)
        if clean is None:
            skipped_reasons.append({"row": i + 2, "reason": reason})  # +2: header + 1-based
        else:
            clean_rows.append(clean)

    db = get_db()
    cur = db.execute(
        "INSERT INTO datasets (name, filename, imported_at, row_count, skipped_count) "
        "VALUES (?, ?, ?, ?, ?)",
        (name, upload.filename, datetime.now(timezone.utc).isoformat(),
         len(clean_rows), len(skipped_reasons)),
    )
    dataset_id = cur.lastrowid
    db.executemany(
        "INSERT INTO cdr_records (dataset_id, phone_number, imei, area, timestamp, "
        "call_type, duration_seconds, other_party, other_imei, other_area) "
        "VALUES (:dataset_id, :phone_number, :imei, :area, :timestamp, :call_type, "
        ":duration_seconds, :other_party, :other_imei, :other_area)",
        [dict(r, dataset_id=dataset_id) for r in clean_rows],
    )
    audit.write_audit(db, current_app.config["USERNAME"], audit.IMPORT,
                      {"dataset_id": dataset_id, "imported": len(clean_rows),
                       "skipped": len(skipped_reasons)})
    db.commit()

    return ok({"dataset_id": dataset_id, "imported": len(clean_rows),
               "skipped": len(skipped_reasons), "skipped_reasons": skipped_reasons}, 201)


@bp.get("/datasets")
@login_required
def list_datasets():
    db = get_db()
    rows = db.execute(
        "SELECT id, name, filename, imported_at, row_count, skipped_count "
        "FROM datasets ORDER BY id"
    ).fetchall()
    return ok([dict(r) for r in rows])


@bp.get("/datasets/<int:dataset_id>/phone-numbers")
@login_required
def dataset_phone_numbers(dataset_id: int):
    db = get_db()
    exists = db.execute("SELECT 1 FROM datasets WHERE id = ?", (dataset_id,)).fetchone()
    if exists is None:
        return err("NOT_FOUND", "dataset not found", 404)
    rows = db.execute(
        "SELECT phone_number, COUNT(*) AS count FROM cdr_records "
        "WHERE dataset_id = ? GROUP BY phone_number ORDER BY phone_number",
        (dataset_id,),
    ).fetchall()
    return ok([dict(r) for r in rows])


@bp.delete("/datasets/<int:dataset_id>")
@login_required
def delete_dataset(dataset_id: int):
    db = get_db()
    cur = db.execute("DELETE FROM datasets WHERE id = ?", (dataset_id,))
    db.commit()
    if cur.rowcount == 0:
        return err("NOT_FOUND", "dataset not found", 404)
    return ok({})
```

- [ ] **Step 5: Uncomment the imports blueprint registration in `app/__init__.py`.**

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/phase2a/test_imports.py -v`
Expected: all passed.

- [ ] **Step 7: Commit**

```bash
git add app/imports.py app/__init__.py tests/phase2a/conftest.py tests/phase2a/test_imports.py
git commit -m "claude: phase2a task 9 - xlsx import pipeline + datasets endpoints"
```

---

## Task 10: Targets blueprint (`targets.py`)

**Files:**
- Create: `app/targets.py`
- Modify: `app/__init__.py` (uncomment `targets_bp`)
- Test: `tests/phase2a/test_targets.py`

**Interfaces:**
- Consumes: `get_db`, `ok/err/login_required`, `audit.*`.
- Produces: blueprint `bp` with `POST /api/targets`, `GET /api/targets`, `DELETE /api/targets/<int:target_id>`.

- [ ] **Step 1: Write the failing test**

Create `tests/phase2a/test_targets.py`:

```python
import io
import pytest
from app import create_app


@pytest.fixture()
def client(app_data_dir):
    app = create_app()
    app.config.update(TESTING=True)
    c = app.test_client()
    c.post("/api/setup", json={"username": "nadim", "password": "hunter2"})
    return c


@pytest.fixture()
def dataset_id(client, sample_xlsx):
    with open(sample_xlsx, "rb") as fh:
        data = {"name": "d", "file": (io.BytesIO(fh.read()), "sample.xlsx")}
    return client.post("/api/imports", data=data,
                       content_type="multipart/form-data").get_json()["data"]["dataset_id"]


def test_create_list_delete_target(client, dataset_id):
    r = client.post("/api/targets", json={"name": "subject A",
                    "dataset_id": dataset_id, "phone_number": "01000001"})
    assert r.status_code == 201
    tid = r.get_json()["data"]["id"]
    assert len(client.get("/api/targets").get_json()["data"]) == 1
    assert client.delete(f"/api/targets/{tid}").status_code == 200
    assert client.get("/api/targets").get_json()["data"] == []


def test_duplicate_pair_conflicts_even_with_new_name(client, dataset_id):
    client.post("/api/targets", json={"name": "first",
                "dataset_id": dataset_id, "phone_number": "01000001"})
    r = client.post("/api/targets", json={"name": "different label",
                    "dataset_id": dataset_id, "phone_number": "01000001"})
    assert r.status_code == 409


def test_missing_dataset_or_number_is_404(client, dataset_id):
    assert client.post("/api/targets", json={"name": "x", "dataset_id": 999,
                       "phone_number": "01000001"}).status_code == 404
    assert client.post("/api/targets", json={"name": "x", "dataset_id": dataset_id,
                       "phone_number": "09999999"}).status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/phase2a/test_targets.py -v`
Expected: FAIL — `app.targets` not importable.

- [ ] **Step 3: Implement targets.py**

Create `app/targets.py`:

```python
"""Targets blueprint: one target per (dataset_id, phone_number)."""

from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, current_app, request

from app import audit, err, get_db, login_required, ok

bp = Blueprint("targets", __name__, url_prefix="/api")


@bp.post("/targets")
@login_required
def create_target():
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    dataset_id = body.get("dataset_id")
    phone_number = body.get("phone_number")
    if not name or dataset_id is None or not phone_number:
        return err("BAD_REQUEST", "name, dataset_id, phone_number required", 400)

    db = get_db()
    if db.execute("SELECT 1 FROM datasets WHERE id = ?", (dataset_id,)).fetchone() is None:
        return err("NOT_FOUND", "dataset not found", 404)
    present = db.execute(
        "SELECT 1 FROM cdr_records WHERE dataset_id = ? AND phone_number = ? LIMIT 1",
        (dataset_id, phone_number),
    ).fetchone()
    if present is None:
        return err("NOT_FOUND", "phone_number not in dataset", 404)
    dup = db.execute(
        "SELECT 1 FROM targets WHERE dataset_id = ? AND phone_number = ?",
        (dataset_id, phone_number),
    ).fetchone()
    if dup is not None:
        return err("CONFLICT", "a target already exists for this phone in this dataset", 409)

    cur = db.execute(
        "INSERT INTO targets (name, dataset_id, phone_number, created_at) VALUES (?, ?, ?, ?)",
        (name, dataset_id, phone_number, datetime.now(timezone.utc).isoformat()),
    )
    tid = cur.lastrowid
    audit.write_audit(db, current_app.config["USERNAME"], audit.TARGET_CREATE,
                      {"target_id": tid, "dataset_id": dataset_id})
    db.commit()
    return ok({"id": tid, "name": name, "dataset_id": dataset_id,
               "phone_number": phone_number}, 201)


@bp.get("/targets")
@login_required
def list_targets():
    db = get_db()
    rows = db.execute(
        "SELECT id, name, dataset_id, phone_number, created_at FROM targets ORDER BY id"
    ).fetchall()
    return ok([dict(r) for r in rows])


@bp.delete("/targets/<int:target_id>")
@login_required
def delete_target(target_id: int):
    db = get_db()
    cur = db.execute("DELETE FROM targets WHERE id = ?", (target_id,))
    if cur.rowcount == 0:
        return err("NOT_FOUND", "target not found", 404)
    audit.write_audit(db, current_app.config["USERNAME"], audit.TARGET_DELETE,
                      {"target_id": target_id})
    db.commit()
    return ok({})
```

- [ ] **Step 4: Uncomment the targets blueprint registration in `app/__init__.py`.**

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/phase2a/test_targets.py -v`
Expected: all passed.

- [ ] **Step 6: Commit**

```bash
git add app/targets.py app/__init__.py tests/phase2a/test_targets.py
git commit -m "claude: phase2a task 10 - targets CRUD (one per dataset+phone, 409 on dup)"
```

---

## Task 11: Detection bridge (`detection_bridge.py`)

**Files:**
- Create: `app/detection_bridge.py`
- Test: `tests/phase2a/test_bridge.py`

**Interfaces:**
- Consumes (read-only) from Phase 1: `detection.detect_home/detect_work/detect_frequent_areas/detect_frequent_confidence/detect_frequent_contacts`, `detection.DetectionResult`, `detection.ContactRank`.
- Produces:
  - `rows_to_frame(rows: list[dict]) -> pandas.DataFrame` — builds the 9-column frame with a datetime `timestamp` exactly as Phase 1's detectors expect.
  - `analyze_frame(df, top_n: int = 5) -> dict` — runs all five detectors and serializes to the §6 JSON shape.
  - `_result_to_dict(r: DetectionResult) -> dict` and `_contact_to_dict(c: ContactRank) -> dict`.

- [ ] **Step 1: Write the failing test**

Create `tests/phase2a/test_bridge.py`:

```python
import os
import sys
import pathlib
import pandas as pd
import pytest

HERE = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE / "phase1_cdr"))

from app import detection_bridge  # noqa: E402
import detection  # noqa: E402  (Phase 1, read-only)


@pytest.fixture()
def user_a_rows():
    csv = HERE / "phase1_cdr" / "sample_data.csv"
    df = pd.read_csv(csv, dtype={"phone_number": str, "imei": str,
                                 "other_party": str, "other_imei": str})
    a = df[df["phone_number"] == "01000001"]
    return a.to_dict(orient="records")


def test_bridge_matches_direct_phase1_call(user_a_rows):
    frame = detection_bridge.rows_to_frame(user_a_rows)
    bridge = detection_bridge.analyze_frame(frame)

    direct_home = detection.detect_home(frame)
    assert bridge["home"]["area"] == direct_home.area
    assert bridge["home"]["confidence"] == direct_home.confidence
    assert bridge["home"]["gates"] == direct_home.gates

    direct_contacts = detection.detect_frequent_contacts(frame)
    assert [c["number"] for c in bridge["frequent_contacts"]] == [c.number for c in direct_contacts]


def test_frequent_areas_shape(user_a_rows):
    frame = detection_bridge.rows_to_frame(user_a_rows)
    out = detection_bridge.analyze_frame(frame)
    assert out["frequent_areas"]
    assert {"area", "count", "share"} <= set(out["frequent_areas"][0].keys())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/phase2a/test_bridge.py -v`
Expected: FAIL — `app.detection_bridge` not importable.

- [ ] **Step 3: Implement detection_bridge.py**

Create `app/detection_bridge.py`:

```python
"""The ONLY seam between the backend and the frozen Phase 1 algorithm.

Pulls a subject's stored CDR rows, rebuilds the DataFrame shape Phase 1 expects,
runs the five detectors, and serializes their dataclasses to JSON-ready dicts.
Phase 1 is imported read-only; nothing under phase1_cdr/ is modified.
"""

from __future__ import annotations

import os
import sys

import pandas as pd

_PHASE1 = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "phase1_cdr")
if _PHASE1 not in sys.path:
    sys.path.insert(0, _PHASE1)

import detection  # noqa: E402

_COLUMNS = [
    "phone_number", "imei", "area", "timestamp", "call_type",
    "duration_seconds", "other_party", "other_imei", "other_area",
]


def rows_to_frame(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(list(rows), columns=_COLUMNS)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["call_type"] = pd.to_numeric(df["call_type"], errors="coerce").astype("Int64").astype(int)
    df["duration_seconds"] = pd.to_numeric(df["duration_seconds"], errors="coerce").fillna(0).astype(int)
    return df


def _result_to_dict(r: "detection.DetectionResult") -> dict:
    return {
        "area": r.area,
        "confidence": r.confidence,
        "confidence_label": r.confidence_label,
        "near_tie": r.near_tie,
        "alternatives": list(r.alternatives),
        "supporting_records": r.supporting_records,
        "total_window_records": r.total_window_records,
        "share": r.share,
        "closeness": r.closeness,
        "density": r.density,
        "gates": r.gates,
    }


def _contact_to_dict(c: "detection.ContactRank") -> dict:
    return {
        "number": c.number, "total": c.total, "call_out": c.call_out,
        "call_in": c.call_in, "sms_out": c.sms_out, "sms_in": c.sms_in,
    }


def analyze_frame(df: pd.DataFrame, top_n: int = 5) -> dict:
    freq_areas = detection.detect_frequent_areas(df, top_n=top_n)
    return {
        "home": _result_to_dict(detection.detect_home(df)),
        "work": _result_to_dict(detection.detect_work(df)),
        "frequent_areas": [
            {"area": a, "count": c, "share": s} for a, c, s in freq_areas
        ],
        "frequent_areas_confidence": _result_to_dict(detection.detect_frequent_confidence(df)),
        "frequent_contacts": [
            _contact_to_dict(c) for c in detection.detect_frequent_contacts(df, top_n=top_n)
        ],
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/phase2a/test_bridge.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add app/detection_bridge.py tests/phase2a/test_bridge.py
git commit -m "claude: phase2a task 11 - detection bridge (only seam to phase1, equivalence-tested)"
```

---

## Task 12: Analysis blueprint (`analysis.py`)

**Files:**
- Create: `app/analysis.py`
- Modify: `app/__init__.py` (uncomment `analysis_bp`)
- Test: `tests/phase2a/test_analysis.py`

**Interfaces:**
- Consumes: `get_db`, `ok/err/login_required`, `audit.*`, `detection_bridge.rows_to_frame/analyze_frame`.
- Produces: blueprint `bp` with `POST /api/targets/<int:target_id>/analyze` and `GET /api/targets/<int:target_id>/result`. `analyze` accepts optional `?top_n=`.

- [ ] **Step 1: Write the failing test**

Create `tests/phase2a/test_analysis.py`:

```python
import io
import pytest
from app import create_app


@pytest.fixture()
def client(app_data_dir):
    app = create_app()
    app.config.update(TESTING=True)
    c = app.test_client()
    c.post("/api/setup", json={"username": "nadim", "password": "hunter2"})
    return c


@pytest.fixture()
def target_id(client, sample_xlsx):
    with open(sample_xlsx, "rb") as fh:
        data = {"name": "d", "file": (io.BytesIO(fh.read()), "sample.xlsx")}
    ds = client.post("/api/imports", data=data,
                     content_type="multipart/form-data").get_json()["data"]["dataset_id"]
    return client.post("/api/targets", json={"name": "A", "dataset_id": ds,
                       "phone_number": "01000001"}).get_json()["data"]["id"]


def test_analyze_returns_full_shape_and_persists(client, target_id):
    r = client.post(f"/api/targets/{target_id}/analyze")
    assert r.status_code == 200
    data = r.get_json()["data"]
    # User A: clean commuter -> Hamra home, High, full gate trace present.
    assert data["home"]["area"] == "Hamra"
    assert data["home"]["confidence"] == "High"
    assert set(data["home"]["gates"]) == {"N", "share", "closeness", "density"}
    assert data["frequent_contacts"]
    # Result is persisted and retrievable.
    got = client.get(f"/api/targets/{target_id}/result")
    assert got.status_code == 200
    assert got.get_json()["data"]["home"]["area"] == "Hamra"


def test_result_404_before_any_analysis(client, target_id):
    assert client.get(f"/api/targets/{target_id}/result").status_code == 404


def test_analyze_unknown_target_404(client):
    assert client.post("/api/targets/999/analyze").status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/phase2a/test_analysis.py -v`
Expected: FAIL — `app.analysis` not importable.

- [ ] **Step 3: Implement analysis.py**

Create `app/analysis.py`:

```python
"""Analysis blueprint: run Phase 1 detection on a target and store the result."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from flask import Blueprint, current_app, request

from app import audit, detection_bridge, err, get_db, login_required, ok

bp = Blueprint("analysis", __name__, url_prefix="/api")


def _target(db, target_id: int):
    return db.execute(
        "SELECT id, name, dataset_id, phone_number FROM targets WHERE id = ?",
        (target_id,),
    ).fetchone()


@bp.post("/targets/<int:target_id>/analyze")
@login_required
def analyze(target_id: int):
    db = get_db()
    target = _target(db, target_id)
    if target is None:
        return err("NOT_FOUND", "target not found", 404)

    try:
        top_n = int(request.args.get("top_n", 5))
    except ValueError:
        top_n = 5

    rows = db.execute(
        "SELECT phone_number, imei, area, timestamp, call_type, duration_seconds, "
        "other_party, other_imei, other_area FROM cdr_records "
        "WHERE dataset_id = ? AND phone_number = ?",
        (target["dataset_id"], target["phone_number"]),
    ).fetchall()

    frame = detection_bridge.rows_to_frame([dict(r) for r in rows])
    result = detection_bridge.analyze_frame(frame, top_n=top_n)
    analyzed_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "target": {"id": target["id"], "name": target["name"],
                   "phone_number": target["phone_number"]},
        "analyzed_at": analyzed_at,
        **result,
    }

    db.execute(
        "INSERT INTO analysis_results (target_id, created_at, result_json) VALUES (?, ?, ?)",
        (target_id, analyzed_at, json.dumps(payload)),
    )
    audit.write_audit(db, current_app.config["USERNAME"], audit.ANALYSIS,
                      {"target_id": target_id})
    db.commit()
    return ok(payload)


@bp.get("/targets/<int:target_id>/result")
@login_required
def latest_result(target_id: int):
    db = get_db()
    if _target(db, target_id) is None:
        return err("NOT_FOUND", "target not found", 404)
    row = db.execute(
        "SELECT result_json FROM analysis_results WHERE target_id = ? "
        "ORDER BY id DESC LIMIT 1",
        (target_id,),
    ).fetchone()
    if row is None:
        return err("NOT_FOUND", "no analysis yet", 404)
    return ok(json.loads(row["result_json"]))
```

- [ ] **Step 4: Uncomment the analysis blueprint registration in `app/__init__.py`.**

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/phase2a/test_analysis.py -v`
Expected: all passed.

- [ ] **Step 6: Commit**

```bash
git add app/analysis.py app/__init__.py tests/phase2a/test_analysis.py
git commit -m "claude: phase2a task 12 - analysis endpoints (run detection, persist, retrieve)"
```

---

## Task 13: Desktop entry point (`main.py`)

**Files:**
- Create: `main.py`
- Test: `tests/phase2a/test_main.py`

**Interfaces:**
- Consumes: `create_app`.
- Produces:
  - `start_server(app, host="127.0.0.1", port=0) -> (server, thread, actual_port)` — starts `werkzeug.serving.make_server` on a daemon thread, returns the live server handle and the OS-assigned port.
  - `wait_until_ready(port, timeout=10.0) -> None` — polls `GET /api/health` until 200.
  - `main() -> None` — wires server + PyWebView window + clean shutdown.

- [ ] **Step 1: Write the failing test**

Create `tests/phase2a/test_main.py`:

```python
import urllib.request
import json
import main as entry
from app import create_app


def test_server_starts_and_health_responds(app_data_dir):
    app = create_app()
    server, thread, port = entry.start_server(app, port=0)
    try:
        entry.wait_until_ready(port, timeout=10.0)
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health") as r:
            body = json.loads(r.read())
        assert body["data"]["status"] == "ok"
        assert port != 0
    finally:
        server.shutdown()
        thread.join(timeout=5)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/phase2a/test_main.py -v`
Expected: FAIL — `main` has no `start_server`.

- [ ] **Step 3: Implement main.py**

Create `main.py`:

```python
"""Desktop entry point: Flask on an ephemeral localhost port + a PyWebView window.

Flask runs on a daemon thread; the PyWebView window is the main thread. Closing
the window returns from webview.start(), after which the server is shut down.
"""

from __future__ import annotations

import threading
import time
import urllib.request

from werkzeug.serving import make_server

from app import create_app


def start_server(app, host: str = "127.0.0.1", port: int = 0):
    server = make_server(host, port, app, threaded=True)
    actual_port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, actual_port


def wait_until_ready(port: int, timeout: float = 10.0) -> None:
    deadline = time.time() + timeout
    url = f"http://127.0.0.1:{port}/api/health"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url) as r:
                if r.status == 200:
                    return
        except Exception:
            time.sleep(0.05)
    raise RuntimeError("server did not become ready in time")


def main() -> None:  # pragma: no cover - requires a display
    import webview

    app = create_app()
    server, thread, port = start_server(app, port=0)
    wait_until_ready(port)
    try:
        webview.create_window("La Passion — CDR", f"http://127.0.0.1:{port}/api/health")
        webview.start()
    finally:
        server.shutdown()
        thread.join(timeout=5)


if __name__ == "__main__":  # pragma: no cover
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/phase2a/test_main.py -v`
Expected: 1 passed.

- [ ] **Step 5: Manual smoke test (developer machine with a display)**

Run: `python main.py`
Expected: a desktop window opens (no browser) showing the `/api/health` JSON `{"ok": true, "data": {"status": "ok"}}`. Close the window; the process exits cleanly.

- [ ] **Step 6: Commit**

```bash
git add main.py tests/phase2a/test_main.py
git commit -m "claude: phase2a task 13 - PyWebView + Flask desktop entry point"
```

---

## Task 14: Full-suite gate — Phase 2A + Phase 1 regression

**Files:**
- Create: `tests/phase2a/test_phase1_regression.py`
- Modify: `README.md` (add a short Phase 2A section + run instructions)

**Interfaces:**
- Consumes: nothing new; runs both suites.

- [ ] **Step 1: Write the Phase 1 regression guard**

Create `tests/phase2a/test_phase1_regression.py`:

```python
"""Guard: the Phase 2A work must not have disturbed Phase 1.

Runs the Phase 1 validation harness (34 checks) as a subprocess and asserts it
exits 0 and reports 34/34. Phase 1's own unit tests are run by the suite command
in Step 3.
"""

import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parents[2]
PHASE1 = HERE / "phase1_cdr"


def test_phase1_harness_still_passes():
    subprocess.run([sys.executable, "dev_fixtures.py"], cwd=PHASE1, check=True)
    proc = subprocess.run(
        [sys.executable, "main.py", "sample_data.csv", "ground_truth.json"],
        cwd=PHASE1, capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "passed (100%)" in proc.stdout
```

- [ ] **Step 2: Run the regression guard**

Run: `pytest tests/phase2a/test_phase1_regression.py -v`
Expected: 1 passed.

- [ ] **Step 3: Run BOTH full suites**

Run:
```bash
pytest tests/phase2a -v
pytest phase1_cdr/tests -v
```
Expected: all Phase 2A tests pass; Phase 1 reports **18 passed**. Confirm no file under `phase1_cdr/` (other than the regenerated `sample_data.csv`/`ground_truth.json`, which are deterministic) shows in `git status`.

- [ ] **Step 4: Verify Phase 1 source is untouched**

Run: `git diff --stat v1.0-phase1 -- phase1_cdr/loader.py phase1_cdr/detection.py phase1_cdr/validate.py phase1_cdr/main.py phase1_cdr/dev_fixtures.py`
Expected: **no output** (no diff) — the Phase 1 algorithm files are byte-identical to the tag.

- [ ] **Step 5: Update README**

Add a short section to the root `README.md` under the Phases table noting Phase 2A is the Flask + PyWebView backend, with run instructions:

```markdown
### Phase 2A — Backend (desktop app)

A Flask backend behind a PyWebView desktop window, over a SQLCipher-encrypted
SQLite database with single-account auth. Run the API tests with
`pytest tests/phase2a`; launch the desktop app with `python main.py`.
See `docs/superpowers/specs/2026-06-24-phase2a-backend-design.md`.
```

- [ ] **Step 6: Commit**

```bash
git add tests/phase2a/test_phase1_regression.py README.md
git commit -m "claude: phase2a task 14 - phase1 regression guard + README + full-suite gate"
```

---

## Self-Review (completed by plan author)

**Spec coverage:**
- §1 desktop window → Task 13. §2 auth → Tasks 4,6,7. §3 import → Tasks 8,9. §4 targets → Task 10. §5 detection integration → Tasks 11,12. §6 JSON API → Tasks 6–12 (all endpoints mapped). Security: bcrypt/envelope → Tasks 2,4; SQLCipher on-disk → Task 3; sessions/CSRF → Task 6; audit → Task 5 + wired in 7,9,10,12; parameterized queries → all DB tasks; no-secrets → Tasks 1,6. §7 bridge → Task 11. §8 tests → every task is TDD; on-disk-encryption proof (Task 3), bridge equivalence (Task 11), Phase 1 regression (Task 14). §9 out-of-scope respected (no UI, no multi-account, no lockout).
- All 15 endpoints present: health/status/setup/login (T6,7), logout/change-password (T7), imports/datasets×3 (T9), targets×3 (T10), analyze/result (T12).

**Placeholder scan:** No TBD/TODO. Each code step shows full code. The only narrative note (Task 7 LOGIN_FAIL) gives the exact replacement code, not a vague instruction. Task 6's "comment out then uncomment" is a concrete sequencing instruction with the exact lines.

**Type consistency:** `db_key: bytes` consistent across crypto/account/storage. `get_db`, `ok`, `err`, `login_required` defined in Task 6 and consumed identically in Tasks 7–12. `rows_to_frame`/`analyze_frame` defined in Task 11 and consumed in Task 12. `write_audit(conn, username, event_type, detail)` consistent. Event-type constants from `audit` used everywhere by name.

**Known sequencing dependency:** Task 6 registers four blueprints that don't exist until Tasks 7–12; handled explicitly by the comment-out/uncomment instructions so every task stays independently green.
