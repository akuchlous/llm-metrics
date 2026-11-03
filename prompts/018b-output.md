# Step 018b Output — SQLAlchemy Core + Alembic Persistence Portability

**Date:** 2026-11-03
**Prompt:** `prompts/018b-sqlalchemy-alembic-persistence.md`
**Status:** Complete — all tests pass, `./run.sh` verified

---

## What was done

Replaced `storage.py`'s direct `sqlite3` usage with SQLAlchemy Core + Alembic, making the persistence layer portable to Cloud SQL PostgreSQL without changing any external semantics.

### New files

| File | Purpose |
|------|---------|
| `alembic.ini` | Alembic config at repo root; URL set programmatically in `_ensure_schema()` |
| `migrations/env.py` | Alembic env; supports `connection` passed via `config.attributes` (online) or URL (CLI/offline) |
| `migrations/versions/f1a2b3c4d5e6_baseline_v7_schema.py` | Baseline revision = v7 schema; `upgrade()` creates both tables + 2 indexes from scratch; used only for fresh databases |

### Changed files

| File | Change |
|------|--------|
| `requirements.txt` | Added `SQLAlchemy==2.0.36`, `alembic==1.14.1`, `Mako==1.3.10`, `typing_extensions==4.16.0` (all with sha256 hashes, D057) |
| `llm_metrics/storage.py` | Full rewrite to SQLAlchemy Core (see below) |
| `tests/test_storage.py` | `init()` no longer wraps Engine in `contextlib.closing`; `sqlite3.IntegrityError` → `sqlalchemy.exc.IntegrityError` in 6 assertions |
| `tests/test_api.py` | `save_attempt()` uses `engine.begin()` + `text()` instead of sqlite3-style `conn.execute("UPDATE ...", ?)` |
| `tests/test_install_requirements.py` | `test_flask_and_exactly_its_dependencies` extended to include the 4 new packages |
| `tests/test_run_script.py` | `test_end_to_end_in_a_copy` copies `alembic.ini` and `migrations/` into the temp repo copy |
| `DECISIONS.md` | D066 updated (deferred → adopted); D018 updated (018b revision note) |
| `PROJECT_STATUS.md` | "Next step" updated to reflect 018b completion |

---

## storage.py architecture

### SQLAlchemy Core table definitions

`_requests` and `_observations` are `Table` objects with `CheckConstraint`s that mirror the original `_REQUESTS_TABLE` SQL string.
The SQL string is kept because it is still used by `_legacy_upgrade()` (v0→v7 migration) and by the `test_version_6_rows_keep_an_unknown_request_profile` test.

### Engine cache

```python
_engines: dict[pathlib.Path, Engine] = {}
```

Module-level cache. `connect(db_path) -> Engine` returns the cached engine or creates a new one on first call, then runs `_ensure_schema()`.

### Schema management (`_ensure_schema`)

Three paths based on what the database already contains:

1. **Fresh database (no tables):** `alembic upgrade head` creates all tables and sets `PRAGMA user_version = 7`.
2. **Pre-Alembic database (tables exist, no `alembic_version` row):** `_legacy_upgrade()` runs the v0→v7 migration chain (same steps as the original `_upgrade()`), then `alembic stamp head` marks it without re-running DDL.
3. **Alembic-managed database (`alembic_version` row present):** `alembic upgrade head` applies any pending revisions (no-op when already at head).

### Legacy upgrade bridge (`_legacy_upgrade`)

Equivalent to the old `_upgrade()` but uses `text()` constructs throughout. Key differences:
- Uses `_columns_of(conn, table)` (wraps `PRAGMA table_info`) instead of direct cursor access.
- v<3 block: handles both the "no requests table at all" case (v0/v1 databases) and the "v2 requests table without outcome" case.
- Ensures `observations` table and its two indexes exist at the end (a v3 database with no observations rows may have no observations table).
- Sets `PRAGMA user_version = SCHEMA_VERSION` at the end.

### Public API changes

| Old | New | Notes |
|-----|-----|-------|
| `connect(db_path) -> sqlite3.Connection` | `connect(db_path) -> Engine` | Return type changed; callers that used it as a context manager must switch to `engine.begin()` |
| `_upgrade(conn)` | `_legacy_upgrade(engine)` | Internal; same v0→v7 semantics |
| `_columns(conn, table)` | `_columns_of(conn, table)` | Internal; renamed for clarity |

All other public function signatures (`save_request`, `load_request`, `load_recent_requests`, `load_observations`, `save_new_observations`, `count_outcomes`, `spend_by_model`, `format_timestamp`) are unchanged.

---

## Test results

```
Ran 344 tests in 9.567s
OK
```

(+3 from `test_run_script.py` with one skipped when `NESTED=1`; 347 total)

`./run.sh` output (abbreviated):
```
✓ Python environment ready
✓ Dependencies ready
✓ Tests passed
Simulated TTFT history: 0 new, 168 already present
✓ Simulated history ready
✓ Starting test measurement
...
Saved attempt 4092639c… with 4 observations to data/llm_metrics.db
```

---

## Known limitations

- `ResourceWarning: unclosed database` appears in test output due to SQLAlchemy's connection pool holding connections open at temp-directory teardown. Not a test failure; pool behavior is correct for production use. Can be eliminated with `NullPool` if it becomes disruptive.
- Only `sqlite+pysqlite` driver is tested; a PostgreSQL driver is not installed yet (out of scope for 018b per prompt constraint).

---

## What stays the same

- All CHECK constraints, NULL semantics, column names, and indexes.
- All 23 columns of the `requests` table; all 8 columns of `observations`.
- The `INSERT OR IGNORE` / `on_conflict_do_nothing()` idempotent seeding in `save_new_observations`.
- Local SQLite file layout and path handling.
- The `PRAGMA user_version` field is kept in sync with `SCHEMA_VERSION` for backward-compatible reads.
- The `test_version_6_rows_keep_an_unknown_request_profile` test that reads the raw SQL string still passes.
