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

### `saved_pair_matches` — click-to-save export staging (contact matcher) — migration 2
| Column | Type | Constraints |
|---|---|---|
| id | INTEGER | PK |
| dataset_id | INTEGER | NOT NULL, FK → `datasets(id)` **ON DELETE CASCADE** |
| target_a_id | INTEGER | NOT NULL, FK → `targets(id)` **ON DELETE CASCADE** |
| target_b_id | INTEGER | NOT NULL, FK → `targets(id)` **ON DELETE CASCADE** |
| created_at | TEXT | NOT NULL |
| result_json | TEXT | NOT NULL (the full match payload, as shown on screen) |
| — | — | **UNIQUE(target_a_id, target_b_id)** |

Pair identity is **order-normalized by the writing repo** (`target_a_id < target_b_id`), so A↔B
and B↔A occupy the same UNIQUE slot and re-saving **replaces**. The export's `Contact matches`
sheet copies `result_json` — it never recomputes.

### `saved_tallies` — click-to-save export staging (frequency explorer) — migration 2
| Column | Type | Constraints |
|---|---|---|
| id | INTEGER | PK |
| target_id | INTEGER | NOT NULL, FK → `targets(id)` **ON DELETE CASCADE** |
| created_at | TEXT | NOT NULL |
| filters_json | TEXT | NOT NULL (the validated filter set the server recomputed from) |
| filter_label | TEXT | NOT NULL (human-readable filter description, shown in the export) |
| tally_json | TEXT | NOT NULL (the stored tally payload) |

Saved tallies accumulate (each is a different question) and are individually deletable from the
Export screen.

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
- **To evolve:** append `(<n>, "<ddl>")` to `MIGRATIONS`; never edit or reorder a released migration.
- The runner is auto-invoked on login via `app/api/guards.py:get_db()` (Phase 3 increment 3.1,
  ADR 0002). **Migration 2** (contact-matcher feature) added `saved_pair_matches` +
  `saved_tallies` — the seam's first real use; existing installs upgrade in place on next login.
