# Database Schema Reference

> **Source of truth is `app/infra/migrations.py`** (`_BASELINE` = migration 1). This file mirrors it for
> readers; if they ever disagree, the code wins. Do **not** hand-edit a live DB — evolve the schema by
> appending a migration (see ADR 0002 and the "Migrations" section below).

## Storage overview

- **One encrypted SQLite database** (`cdr.db`) via **SQLCipher** — the whole file is encrypted with a
  random 256-bit key (`app/infra/storage.py`). The key never touches disk in the clear.
- **`auth.json` sidecar** — *not* in the DB. Holds non-secret account material: `username`,
  `bcrypt_hash`, `kdf_salt`, `db_key_nonce`, `wrapped_db_key`, `created_at` (all binary base64-encoded).
  The DB key is stored only in AES-GCM-wrapped form here (`app/auth/account.py`).
- **`login_failures.log` sidecar** — plaintext, append-only, best-effort failed-login trail (the
  encrypted `audit_log` is unreachable before a successful unlock).
- Location: `%LOCALAPPDATA%\NexuslinkCDR` (Windows) or `~/.nexuslinkcdr` (else), overridable via
  `APP_DATA_DIR` (`app/infra/config.py`).

Connection pragmas on every open (`storage.connect`): `PRAGMA key`, `busy_timeout = 5000`,
`foreign_keys = ON`, `row_factory = Row`.

## Tables

### `datasets` — one imported .xlsx workbook
| Column | Type | Constraints |
|---|---|---|
| id | INTEGER | PK |
| name | TEXT | NOT NULL |
| filename | TEXT | NOT NULL |
| imported_at | TEXT | NOT NULL (ISO-8601 UTC) |
| row_count | INTEGER | NOT NULL |
| skipped_count | INTEGER | NOT NULL |

### `cdr_records` — validated CDR rows
| Column | Type | Constraints |
|---|---|---|
| id | INTEGER | PK |
| dataset_id | INTEGER | NOT NULL, FK → `datasets(id)` **ON DELETE CASCADE** |
| phone_number | TEXT | NOT NULL |
| imei | TEXT | nullable |
| area | TEXT | NOT NULL |
| timestamp | TEXT | NOT NULL (ISO-8601, **naive** local) |
| call_type | INTEGER | NOT NULL |
| duration_seconds | INTEGER | NOT NULL (0 … int64 max) |
| other_party | TEXT | nullable |
| other_imei | TEXT | nullable |
| other_area | TEXT | nullable |

Index: `idx_records_dataset_phone ON cdr_records(dataset_id, phone_number)` — the hot path for both
the phone-number rollup and per-target record reads.

### `targets` — a subject to analyze within a dataset
| Column | Type | Constraints |
|---|---|---|
| id | INTEGER | PK |
| name | TEXT | NOT NULL |
| dataset_id | INTEGER | NOT NULL, FK → `datasets(id)` **ON DELETE CASCADE** |
| phone_number | TEXT | NOT NULL |
| created_at | TEXT | NOT NULL |
| — | — | **UNIQUE(dataset_id, phone_number)** |

### `analysis_results` — stored detector output (append-only; latest wins)
| Column | Type | Constraints |
|---|---|---|
| id | INTEGER | PK |
| target_id | INTEGER | NOT NULL, FK → `targets(id)` **ON DELETE CASCADE** |
| created_at | TEXT | NOT NULL |
| result_json | TEXT | NOT NULL (the full analyze payload) |

`GET /result` returns the highest-`id` row for the target (`ORDER BY id DESC LIMIT 1`). Re-analysis
inserts a new row rather than updating — history is retained even though only the latest is surfaced.

### `audit_log` — in-DB (encrypted) audit trail
| Column | Type | Constraints |
|---|---|---|
| id | INTEGER | PK |
| ts | TEXT | NOT NULL (ISO-8601 UTC) |
| username | TEXT | NOT NULL |
| event_type | TEXT | NOT NULL (see event list in `app/audit/log.py`) |
| detail | TEXT | nullable (JSON) |

## Migrations

- Schema version lives in SQLite's `PRAGMA user_version` (encrypted with the file; no extra table).
- **Migration 1 IS this baseline**, verbatim and `IF NOT EXISTS`, so a fresh DB and an exact Phase-2A DB
  both converge on it.
- A pre-versioning DB (`user_version == 0`, tables present) is *adopted* only after its full-DDL
  fingerprint matches the baseline (`_assert_matches_baseline`) — drift fails loudly.
- Each migration's DDL + version bump run in one `BEGIN IMMEDIATE … COMMIT`.
- **To evolve:** append `(2, "<ddl>")` to `MIGRATIONS`; never edit or reorder a released migration.
- The runner is built (`migrate()`); it is **not yet auto-invoked on login** — that one-line wiring in
  `app/api/guards.py:get_db()` is the first Phase-3 step (ADR 0002).
