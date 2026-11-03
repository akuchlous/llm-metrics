# Step 018c Output — PostgreSQL-Ready Storage Connection and Dialect Correctness

**Date:** 2026-11-03
**Prompt:** `prompts/018c-postgresql-storage-readiness.md`
**Status:** Complete — 359 tests pass, `./run.sh` verified

---

## What was done

Made the existing storage layer genuinely capable of using a PostgreSQL URL
without changing any external semantics for local SQLite. No Cloud SQL
provisioning, no paid calls.

### Changed files

| File | Change |
|------|--------|
| `requirements.txt` | Added `psycopg2-binary==2.9.10` with Linux x86_64 cp313 hash (D057) |
| `llm_metrics/config.py` | Added `DATABASE_URL_VARIABLE`, `get_database_url()` |
| `llm_metrics/storage.py` | See below (6 targeted changes) |
| `llm_metrics/benchmark.py` | `db_path: pathlib.Path` → `db_ref: pathlib.Path | str`; `_db_display()` helper; credential-safe display |
| `llm_metrics/__main__.py` | `get_db_path()` → `get_database_url()` |
| `llm_metrics/real_benchmark.py` | `get_db_path()` → `get_database_url()` |
| `llm_metrics/seed_history.py` | `get_db_path()` → `get_database_url()`; credential-safe display |
| `llm_metrics/web.py` | `create_app()` uses `get_database_url()` when no explicit path; `_db_path()` return type updated |
| `DECISIONS.md` | D066 updated with 018c dialect-correctness details |
| `PROJECT_STATUS.md` | Current state updated to 018c |
| `tests/test_config.py` | New `GetDatabaseUrlTest` (7 tests) |
| `tests/test_storage.py` | New `DialectAndSchemaParityTest` (4 tests) |
| `tests/test_web.py` | 2 assertions updated for string URL in `app.config[DB_PATH_KEY]` |
| `tests/test_install_requirements.py` | `psycopg2-binary` added to expected package set |

---

## storage.py changes

### 1. Imports
Added `ForeignKey` from SQLAlchemy and `from sqlalchemy.dialects.postgresql import insert as _pg_insert`.

### 2. `_observations` FK fix
```python
# Before:
Column("request_id", Text),
# After:
Column("request_id", Text, ForeignKey("requests.id")),
```
This reconciles the Table metadata with the Alembic baseline definition
(`f1a2b3c4d5e6` already has `ForeignKeyConstraint(["request_id"], ["requests.id"])`).
SQLite does not enforce FK constraints by default, so no existing behaviour changes.

### 3. Engine cache and `connect()`
- Cache type changed: `dict[pathlib.Path, Engine]` → `dict[str, Engine]` (keyed by URL string).
- `connect(db_ref: pathlib.Path | str)`: Paths are resolved to absolute form and the URL is
  built as `sqlite:///...`; string URLs are used as-is. For SQLite URLs (both path and string
  forms) the parent directory is created if missing. Credentials never appear in errors.

### 4. `_ensure_schema()` dialect-aware
- SQLite: full existing logic (PRAGMA user_version check, legacy bridge, fresh-DB stamp).
- PostgreSQL: `PRAGMA user_version` and `_legacy_upgrade()` are never called. Fresh DB → `upgrade head`. Tables without alembic_version → stamp as head (operator-managed). Alembic-managed → `upgrade head`.

### 5. `save_new_observations()` dialect-aware
```python
if engine.dialect.name == "postgresql":
    stmt = _pg_insert(_observations).on_conflict_do_nothing()
else:
    stmt = _sqlite_insert(_observations).on_conflict_do_nothing()
```

### 6. Public function signatures
All 7 public functions (`save_request`, `save_new_observations`, `load_observations`,
`load_request`, `load_recent_requests`, `count_outcomes`, `spend_by_model`) updated from
`db_path: pathlib.Path` to `db_path: pathlib.Path | str`.

---

## Configuration

| Variable | Precedence | Description |
|---|---|---|
| `LLM_METRICS_DATABASE_URL` | 1 (highest) | SQLAlchemy URL; `sqlite` or `postgresql`/`postgresql+psycopg2` only |
| `LLM_METRICS_DB_PATH` | 2 | SQLite file path (converted to `sqlite:///...`) |
| default | 3 (lowest) | `data/llm_metrics.db` |

`get_database_url()` never echoes the URL value in error messages.

---

## PostgreSQL driver

| Package | Version | Platform | sha256 |
|---------|---------|----------|--------|
| `psycopg2-binary` | 2.9.10 | Linux x86_64 cp313 | `8608c078134f0b3cbd9f89b34bd60a943b23fd33cc5f065e8d5f840061bd0673` |

---

## Migration management note

`_ensure_schema()` runs `alembic upgrade head` per engine creation (once, then cached). For
production Cloud SQL this is safe for forward-only migrations with no destructive DDL. For
migrations that drop columns or change constraints, the operator should apply the migration
before routing traffic (separate `alembic upgrade head` in a pre-traffic step), not rely on
per-startup auto-migration. This step does not build any deployment infrastructure.

---

## Test matrix

| Test scope | Method | PostgreSQL? |
|---|---|---|
| URL selection / scheme validation | `test_config.py:GetDatabaseUrlTest` | No (no live DB) |
| Credential redaction in errors | `test_config.py:GetDatabaseUrlTest` | No |
| FK metadata matches Alembic baseline | `test_storage.py:DialectAndSchemaParityTest` | No |
| PostgreSQL DDL compilation (both tables) | `test_storage.py:DialectAndSchemaParityTest` | Compile only |
| PostgreSQL INSERT ON CONFLICT compilation | `test_storage.py:DialectAndSchemaParityTest` | Compile only |
| SQLite INSERT OR IGNORE compilation | `test_storage.py:DialectAndSchemaParityTest` | N/A |
| All 347 existing storage/upgrade/read tests | `test_storage.py` | No (SQLite only) |
| `./run.sh` end-to-end | `test_run_script.py` | No (SQLite only) |
| Web app DB path config | `test_web.py:AppFactoryTest` | No |

**PostgreSQL integration not yet verified** — no live server available. All PostgreSQL-specific
tests verify SQL compilation only, not actual query execution.

---

## Preserved invariants

- Local SQLite behavior is entirely unchanged: same paths, same legacy upgrades, same CHECK constraints.
- `PRAGMA user_version` is kept in sync for backward-compatible reads.
- No credentials logged or printed anywhere in the code path.
- No guessed or backfilled historical facts; NULL means unknown.
- All existing test assertions pass unchanged except 2 in `test_web.py` (which now check for a string URL instead of a `pathlib.Path`, because `create_app()` with no arg now stores a URL string).

---

## Limits

- Only `cp313 manylinux_2_17_x86_64` wheel for psycopg2-binary is pinned; add hashes for other platforms as needed.
- PostgreSQL integration not yet verified; tested by dialect compilation only.
- Production migration management is the operator's responsibility (not automated per-startup for destructive migrations).

---

## Commit

See `git log` for the 018c commit SHA.

## Recommended next step

Step 018d: provision a Cloud SQL PostgreSQL instance, set `LLM_METRICS_DATABASE_URL` in the deployment environment, run `alembic upgrade head` as a pre-traffic migration step, and deploy the scheduler and web server to Cloud Run.
