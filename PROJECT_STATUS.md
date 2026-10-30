# Project status

_Last updated: Step 010 — 2026-10-30_

## Current state

**Step 010 complete:** each measured request is stored as a `requests` row with its own id, simulated input/output token counts, the requested output cap, and its cost (with the prices used), linked to its total latency / TTFT / chunk-throughput observations. A `/requests` view lists recent individual requests. Schema version 2.

Working:
- `./run.sh` creates/reuses `.venv`, runs tests, seeds simulated TTFT history (test only, idempotent), measures one request (tokens, total latency, TTFT, throughput, cost), then serves the dashboard at `http://127.0.0.1:8000/` until Ctrl+C.
- `APP_ENV=test` is the safe default; `prod` refuses to run.
- Each successful run saves one `requests` row (id, tokens, max output tokens, prices, costs) and up to three linked observations (`total_latency`, `ttft`, `output_chunks_per_s`), in one transaction with one `recorded_at`. Throughput is omitted when undefined.
- `python3 -m llm_metrics.seed_history` adds 168 hourly simulated TTFT rows (2026-10-23 00:00 to 2026-10-29 23:00 UTC); re-running adds nothing.
- Dashboard (`python -m llm_metrics.dashboard`, `/?window=24h|7d|30d&metric=total_latency|ttft|output_chunks_per_s`): `TEST / SIMULATED DATA` label, metric and window links, latest value, nearest-rank p50/p95/p99 with `n` (in the metric's unit), and an SVG chart spanning the window, all from the same `test`/dummy/<metric> rows with `now − window <= recorded_at <= now`. Invalid or repeated `window`/`metric` → HTTP 400. Standard library only; no JavaScript.
- Recent requests view (`/requests`): the 20 most recent `test` requests with tokens, total latency (primary), TTFT, chunk throughput, and costs; labelled simulated.
- 99 standard-library `unittest` tests (pass on Python 3.11 and 3.13).
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
  providers.py     provider interface (text chunks + final Usage); DummyProvider with simulated tokenizer and output cap
  latency.py       METRICS catalogue (label, unit); measure_request: token facts + metrics in one pass
  pricing.py       all prices (USD per 1M tokens) + request_cost
  storage.py       SQLite init + transactional versioned upgrade; save_request; time-window reads; request reads
  seed_history.py  deterministic simulated TTFT history + seed command
  dashboard.py     aggregate view (/) + recent requests (/requests); http.server on 127.0.0.1
  percentiles.py   nearest-rank percentile (no HTML)
  config.py        environment, DB path, dashboard port
  __main__.py      CLI
tests/             automated tests
prompts/           prompt history and guidance
design-questions/  interview-style design questions per step
data/              runtime DB; git-ignored
```

Flow: `environment → provider → measure_request (one stream: Usage + metrics) → price_for + request_cost → print → save_request (request + observations, one transaction)`; dashboard: `GET /?window=&metric= → parse_query → window_bounds(now) → load_observations(metric, start, end) → render HTML/SVG`.

SQLite (schema version 2, `PRAGMA user_version`; older databases upgrade in place, transactionally, keeping all rows):
- `requests`: `id` (UUID hex), `recorded_at`, `environment`, `provider`, `model`, `input_tokens`, `requested_max_output_tokens`, `output_tokens`, `input_price_per_1m`, `output_price_per_1m`, `input_cost`, `output_cost`, `total_cost` (USD, unrounded).
- `observations`: `id`, `recorded_at` (UTC), `environment`, `provider`, `model`, `metric`, `value` (unit fixed by `metric`), `request_id` (NULL for pre-Step-010 and seeded rows).
A unique index on observations (`recorded_at`, `environment`, `provider`, `model`, `metric`) lets seeding skip existing rows.

`LLM_METRICS_DB_PATH` can override the default DB path; tests use temporary databases. SQL values are parameterized.

## Known limitations

- Simulated provider only; one request per run, with a fixed prompt and `MAX_OUTPUT_TOKENS = 64`.
- Token counts come from a simulated tokenizer (1 token per 4 characters) and prices are simulated; neither matches a real provider.
- No token throughput (`output_tokens_per_s`): the provider gives no per-token timing.
- Observations recorded before Step 010 and seeded history have no request details.
- Simulated history exists for TTFT only; total latency and throughput have only live measurements.
- Throughput counts stream chunks, not provider tokens; the dummy's chunks are fixed (5 per response).
- Percentiles are reported the same way for every metric; for throughput (higher is better) the low tail (e.g. p5) would be more informative and is not shown.
- Simulated history uses a fixed past week; it moves out of the 24h/7d windows over time (after 2026-11-28 23:00 UTC it is outside all windows).
- Seeded and live dummy rows are both `test`/`dummy`; they are told apart only by timestamp (seeded rows are on the hour, before 2026-10-30).
- Dashboard has three fixed windows only; no custom ranges, provider filters, zoom, tooltips, or auto-refresh (reload the page).
- Within a window, seeded and live rows are still mixed (no source filter).
- With fewer than 100 observations, nearest-rank p99 equals the maximum.
- Printing the page drops the label's background colour (browser print default).
- Migrations are hand-written upgrade steps in `storage._upgrade`; each schema change needs a new version and an upgrade test.
- A storage failure currently surfaces as a traceback after measurement output.
- `.venv` has no pip until a dependency is justified.

## Next step

To be defined by the next numbered prompt after review.

Do not yet add real providers, scheduler, Docker, cloud deployment, authentication, or workload dimensions (request category, token sizes, execution location).
