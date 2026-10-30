# Project status

_Last updated: Step 003 — 2026-10-30_

## Objective

Independently measure LLM provider performance: TTFT, throughput, latency, reliability, and price. Build in small, tested steps.

## Current milestone

**Step 003 complete:** successful TTFT observations are saved to local SQLite.

Working now:
- Dummy streaming provider; no network calls.
- TTFT via `time.perf_counter()`.
- `APP_ENV=test` by default; `prod` safely refuses to run and saves nothing.
- `python -m llm_metrics` CLI.
- `./run.sh` creates/reuses `.venv`, runs tests, then measures TTFT.
- Each successful measurement is appended to `data/llm_metrics.db`.
- 28 standard-library `unittest` tests.

## Run

Requires Linux/Chromebook Linux and Python 3.10+.

```bash
git clone https://github.com/akuchlous/llm-metrics.git
cd llm-metrics
./run.sh
```

Output ends with:

```text
TTFT: 100.3 ms
Saved observation to data/llm_metrics.db
```

Tests only: `python -m unittest -v`.

Current output is simulated and does **not** represent real LLM performance.

## Architecture

```text
run.sh                 local entry point: venv -> tests -> measurement
llm_metrics/
  providers.py         LLMProvider + DummyProvider
  ttft.py              TTFT measurement (no storage code)
  storage.py           SQLite schema, connect(), save_observation()
  config.py            test/prod configuration, database path
  __main__.py          CLI
tests/                 automated tests
prompts/               development prompt history
data/                  runtime SQLite database (git-ignored)
```

Flow: `APP_ENV → provider → measure_ttft → CLI prints → save_observation`.

TTFT result: `provider`, `model`, `metric`, `value_ms`.

## Storage

- **Location:** `data/llm_metrics.db` under the repo root. `LLM_METRICS_DB_PATH` overrides it (tests use this).
- **Initialization:** `storage.connect()` creates `data/` and runs `CREATE TABLE IF NOT EXISTS` on every open. Idempotent; no manual setup or migrations.
- **Persistence:** after `measure_ttft` succeeds, the CLI calls `save_observation()`, which inserts one row with parameterized SQL and a UTC timestamp.
- **Schema:**

```sql
CREATE TABLE IF NOT EXISTS observations (
    id          INTEGER PRIMARY KEY,
    recorded_at TEXT    NOT NULL,   -- UTC, e.g. 2026-10-30T00:43:46.279219Z
    environment TEXT    NOT NULL CHECK (environment IN ('test', 'prod')),
    provider    TEXT    NOT NULL,
    model       TEXT    NOT NULL,
    metric      TEXT    NOT NULL,
    value_ms    REAL    NOT NULL
)
```

## Tests (28)

All use temporary databases; none touch `data/llm_metrics.db`.

- `test_providers.py` (3): dummy tokens, name, model.
- `test_ttft.py` (4): result fields, positive value, delay reflected, empty stream fails.
- `test_config.py` (8): `APP_ENV` parsing/defaults/errors, provider selection, DB path default and override.
- `test_storage.py` (6): fresh init, idempotent init, stored fields and UTC timestamp, append without overwrite, unknown environment rejected, values stored literally (not as SQL).
- `test_cli.py` (4): output; one correct row saved; `prod` and invalid env exit 2 without creating a database.
- `test_run_script.py` (3): executable, valid syntax, end-to-end in a temp copy (creates/reuses `.venv`, saves a row per run, stops without saving when a test fails).

## Constraints / limitations

- Simulated provider only; one TTFT measurement per run.
- Data is written but not yet read or displayed; too little history for graphs.
- `value_ms` assumes millisecond metrics; no migrations for future schema changes.
- If saving fails (e.g. `data/` not writable), the CLI exits with a traceback after printing the measurement.
- No dashboard, real provider, or production execution yet.
- Standard library only; `.venv` currently has no pip.
- `.env`, `.venv`, and `data/` are ignored; no secrets are used.
- `./run.sh` must remain working after every step.

See `DECISIONS.md` for engineering principles and durable decisions.

## Next step

**Step 004 — deterministic historical simulated TTFT data.** Add a command that inserts a fixed, reproducible set of past simulated TTFT observations (e.g. hourly for the last 7 days, fixed random seed) with `environment = 'test'`. Re-running must not create duplicates. Tests use temporary databases; `./run.sh` stays unchanged.

Do not yet add a dashboard/web server, other metrics, percentiles, real providers, scheduler, Docker, or cloud deployment.
