# Project status

_Last updated: Step 008 — 2026-10-30_

## Current state

**Step 008 complete:** each run measures TTFT and total response latency from one streamed request, saves both, and the dashboard can show either metric for a 24h / 7d / 30d window.

Working:
- `./run.sh` creates/reuses `.venv`, runs tests, seeds simulated TTFT history (test only, idempotent), measures TTFT + total latency, then serves the dashboard at `http://127.0.0.1:8000/` until Ctrl+C.
- `APP_ENV=test` is the safe default; `prod` refuses to run.
- Each successful run appends two rows (`ttft`, `total_latency`, same `recorded_at`, one transaction) to `data/llm_metrics.db`.
- `python3 -m llm_metrics.seed_history` adds 168 hourly simulated TTFT rows (2026-10-23 00:00 to 2026-10-29 23:00 UTC); re-running adds nothing.
- Dashboard (`python -m llm_metrics.dashboard`, `/?window=24h|7d|30d&metric=ttft|total_latency`): `TEST / SIMULATED DATA` label, metric and window links, latest value, nearest-rank p50/p95/p99 with `n`, and an SVG chart spanning the window, all from the same `test`/dummy/<metric> rows with `now − window <= recorded_at <= now`. Invalid or repeated `window`/`metric` → HTTP 400. Standard library only; no JavaScript.
- 70 standard-library `unittest` tests.
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

Seed simulated history by hand (`./run.sh` already does this in test mode): `python3 -m llm_metrics.seed_history`.

`LLM_METRICS_PORT` changes the dashboard port (default `8000`, `0` = any free port).

## Architecture

```text
run.sh             venv -> tests -> seed (test) -> measurement -> dashboard
llm_metrics/
  providers.py     DummyProvider (first-token + inter-token delays) + provider interface
  latency.py       measure_latency: TTFT + total latency in one pass
  storage.py       SQLite initialization, batch insert, time-window filtered read
  seed_history.py  deterministic simulated TTFT history + seed command
  dashboard.py     HTML/SVG rendering + http.server on 127.0.0.1
  percentiles.py   nearest-rank percentile (no HTML)
  config.py        environment, DB path, dashboard port
  __main__.py      CLI
tests/             automated tests
prompts/           prompt history and guidance
design-questions/  interview-style design questions per step
data/              runtime DB; git-ignored
```

Flow: `environment → provider → measure_latency (one stream) → print → persist both`; dashboard: `GET /?window=&metric= → parse_query → window_bounds(now) → load_observations(metric, start, end) → render HTML/SVG`.

SQLite table `observations` stores:
`id`, `recorded_at` (UTC), `environment`, `provider`, `model`, `metric`, `value_ms`.
A unique index on (`recorded_at`, `environment`, `provider`, `model`, `metric`) lets seeding skip existing rows; it is added automatically to older databases.

`LLM_METRICS_DB_PATH` can override the default DB path; tests use temporary databases. SQL values are parameterized.

## Known limitations

- Simulated provider only; one request (two observations) per run.
- Simulated history exists for TTFT only; total latency has only live measurements.
- Simulated history uses a fixed past week; it moves out of the 24h/7d windows over time (after 2026-11-28 23:00 UTC it is outside all windows).
- Seeded and live dummy rows are both `test`/`dummy`; they are told apart only by timestamp (seeded rows are on the hour, before 2026-10-30).
- Dashboard has three fixed windows only; no custom ranges, provider filters, zoom, tooltips, or auto-refresh (reload the page).
- Within a window, seeded and live rows are still mixed (no source filter).
- With fewer than 100 observations, nearest-rank p99 equals the maximum.
- Printing the page drops the label's background colour (browser print default).
- `value_ms` supports millisecond metrics; other units will require a schema decision.
- No migration mechanism yet.
- A storage failure currently surfaces as a traceback after measurement output.
- `.venv` has no pip until a dependency is justified.

## Next step

To be defined by the next numbered prompt after review.

Do not yet add real providers, scheduler, Docker, cloud deployment, authentication, or workload dimensions (request category, token sizes, execution location).
