# Project status

_Last updated: Step 005 — 2026-10-30_

## Current state

**Step 005 complete:** a local browser dashboard shows simulated TTFT over time.

Working:
- `./run.sh` creates/reuses `.venv`, runs tests, measures TTFT, then serves the dashboard at `http://127.0.0.1:8000/` until Ctrl+C.
- `APP_ENV=test` is the safe default; `prod` refuses to run.
- Successful measurements append to `data/llm_metrics.db`.
- `python3 -m llm_metrics.seed_history` adds 168 hourly simulated TTFT rows (2026-10-23 00:00 to 2026-10-29 23:00 UTC); re-running adds nothing.
- Dashboard (`python -m llm_metrics.dashboard`): `TEST / SIMULATED DATA` label, provider/model, latest TTFT, SVG line chart of all `test`/dummy/`ttft` rows. Standard library only; no JavaScript.
- 47 standard-library `unittest` tests.
- No network calls, secrets, or third-party dependencies.

Current data is **simulated** and does not represent real LLM performance.

## Run

Requires Linux/Chromebook Linux and Python 3.10+.

```bash
git clone https://github.com/akuchlous/llm-metrics.git
cd llm-metrics
./run.sh
```

Tests only: `python -m unittest -v`.

Seed simulated history (optional, `APP_ENV=test` only; recommended once so the chart has data): `python3 -m llm_metrics.seed_history`.

`LLM_METRICS_PORT` changes the dashboard port (default `8000`, `0` = any free port).

## Architecture

```text
run.sh             venv -> tests -> measurement -> dashboard
llm_metrics/
  providers.py     DummyProvider + provider interface
  ttft.py          TTFT measurement
  storage.py       SQLite initialization, inserts, filtered read
  seed_history.py  deterministic simulated TTFT history + seed command
  dashboard.py     HTML/SVG rendering + http.server on 127.0.0.1
  config.py        environment, DB path, dashboard port
  __main__.py      CLI
tests/             automated tests
prompts/           prompt history and guidance
data/              runtime DB; git-ignored
```

Flow: `environment → provider → measure TTFT → print → persist`; dashboard: `HTTP GET / → load_observations → render HTML/SVG`.

SQLite table `observations` stores:
`id`, `recorded_at` (UTC), `environment`, `provider`, `model`, `metric`, `value_ms`.
A unique index on (`recorded_at`, `environment`, `provider`, `model`, `metric`) lets seeding skip existing rows; it is added automatically to older databases.

`LLM_METRICS_DB_PATH` can override the default DB path; tests use temporary databases. SQL values are parameterized.

## Known limitations

- Simulated provider only; one TTFT observation per run.
- Simulated history uses a fixed past week; it does not move with the current date.
- Seeded and live dummy rows are both `test`/`dummy`; they are told apart only by timestamp (seeded rows are on the hour, before 2026-10-30).
- Dashboard has one fixed view (all simulated dummy TTFT); no filters, zoom, tooltips, or auto-refresh (reload the page).
- `./run.sh` does not seed, so a fresh clone's chart has only the live runs until `seed_history` is run.
- Opening the dashboard from ChromeOS Chrome on a real Chromebook is not yet verified.
- `value_ms` supports millisecond metrics; other units will require a schema decision.
- No migration mechanism yet.
- A storage failure currently surfaces as a traceback after measurement output.
- `.venv` has no pip until a dependency is justified.

## Next step

To be defined by the next numbered prompt after review. A natural candidate: a second metric (e.g. total response time) for the dummy provider, displayed on the same dashboard.

Do not yet add real providers, scheduler, Docker, cloud deployment, authentication, or workload dimensions (request category, token sizes, execution location).
