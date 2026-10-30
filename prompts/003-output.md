# Step 003 — Implementation report

Commit: `7c58e1a`. Prompt: `003-sqlite-storage.md`.

## What was implemented

Each successful TTFT measurement is appended to SQLite at `data/llm_metrics.db` (git-ignored, created automatically). The CLI prints `Saved observation to data/llm_metrics.db`.

## Files

- `llm_metrics/storage.py` (new) — schema, `connect()` (initializes on every open), `save_observation()`.
- `llm_metrics/config.py` — `DEFAULT_DB_PATH`, `get_db_path()` with the `LLM_METRICS_DB_PATH` override.
- `llm_metrics/__main__.py` — saves after a successful measurement.
- `tests/test_storage.py` (new); `test_cli.py`, `test_config.py` and `test_run_script.py` were extended.
- `.gitignore` (`data/`), `README.md`, `PROJECT_STATUS.md`, `DECISIONS.md` (D016–D021).

## Tests / run

- 28 tests, OK.
- Clean `./run.sh` run (after deleting `.venv` and `data/`): two runs gave two correct rows; `APP_ENV=prod` added none.
- After the full suite, `data/` still did not exist, so tests never touch the real database.
- Security scan: no database, venv, `.env` or cache files staged; no secret-like strings; no SQL built from strings.

## Design decisions and why

- **Path anchored to the repo root**, not the current directory, so the same file is used however the CLI is started.
- **`environment` column with a `CHECK` constraint**, so simulated rows can't be mistaken for future prod rows.
- **`value_ms`** matches the result dict and makes the unit explicit.
- **`connect()` creates the table if missing on every open.** No setup step and no migrations.
- **`LLM_METRICS_DB_PATH`** exists so CLI subprocess tests can use a temporary database.

## Alternatives / tradeoffs

- A separate `init_db()` was first written but used only by tests. It was replaced by a single public `connect()` that both the app and tests use.
- `recorded_at` is the save time, about 100 ms after the request started, not the request start time. This kept `measure_ttft` unchanged.
- `INTEGER PRIMARY KEY` without `AUTOINCREMENT`, which is SQLite's recommended default.

## Limitations / review questions

- A metric in a non-millisecond unit would need a schema change, and there is no migration path.
- If saving fails, the CLI prints a traceback after the measurement output.
- While this step was in progress, `DECISIONS.md` and `PROJECT_STATUS.md` were condensed on `main`. The step was rebased, and its additions were rewritten in the condensed style. The decision numbers drafted locally were renumbered to D016–D021.
