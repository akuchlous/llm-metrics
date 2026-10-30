# Project status

_Last updated: Step 012 — 2026-10-30_

## Current state

**Step 012 complete:** first real provider (OpenAI `gpt-6-luna`, Responses API, standard library only) behind the existing boundary, callable only via `python -m llm_metrics.real_smoke` (one paid call, key from `OPENAI_API_KEY`, stored as `prod`); Benchmark API Spend page; real and simulated data labelled and separated. **The real smoke call has not been run yet** (no key and OpenAI hosts blocked in the implementation environment), and the gpt-6-luna price ($0.10 / $0.50 per 1M) is **not yet verified** against the official page.

Working:
- `./run.sh` creates/reuses `.venv`, runs tests, seeds simulated TTFT history (test only, idempotent), makes one benchmark attempt (outcome, tokens, total latency, TTFT, throughput, cost), then serves the dashboard at `http://127.0.0.1:8000/` until Ctrl+C.
- `APP_ENV=test` is the safe default; `APP_ENV=prod ./run.sh` refuses to run (no implicit spend).
- `python -m llm_metrics.real_smoke`: exactly one real OpenAI `gpt-6-luna` request (requires `OPENAI_API_KEY`; refuses without it), stored with `environment = 'prod'`.
- Each run saves one `requests` row (attempt) with its `outcome`. Success: tokens, max output tokens, prices, costs, and up to three linked observations (`total_latency`, `ttft`, `output_chunks_per_s`), in one transaction. Failure: category, `failed_after_ms`, prices and cap; tokens/costs NULL (unknown); no observations.
- `python3 -m llm_metrics.seed_history` adds 168 hourly simulated TTFT rows (2026-10-23 00:00 to 2026-10-29 23:00 UTC); re-running adds nothing.
- Dashboard (`python -m llm_metrics.dashboard`, `/?window=24h|7d|30d&metric=total_latency|ttft|output_chunks_per_s`): `TEST / SIMULATED DATA` label, metric and window links, observed benchmark success rate over all attempts in the window (count, rate, failures by category; no attempts → no rate), then for successful attempts only: latest value, nearest-rank p50/p95/p99 with `n` (in the metric's unit), and an SVG chart spanning the window, all from the same `test`/dummy/<metric> rows with `now − window <= recorded_at <= now`. Invalid or repeated `window`/`metric` → HTTP 400. Standard library only; no JavaScript.
- Recent requests view (`/requests`): the 20 most recent `test` attempts with outcome (FAILED + category), tokens, total latency (primary), TTFT, chunk throughput, costs, and failed-after time; unknown values shown as "—"; labelled simulated.
- Benchmark API Spend (`/spend?window=`, default 30d, real data only): per provider/model successful paid calls, tokens, known total cost, failed attempts (cost unknown), and a grand total.
- Pages are labelled TEST / SIMULATED DATA or REAL PROVIDER DATA; `/requests?data=simulated|real` switches population.
- 147 standard-library `unittest` tests (pass on Python 3.11 and 3.13); none touch the network.
- No third-party dependencies. Network and secrets are used only by `real_smoke`.

Data from `./run.sh` is **simulated** and does not represent real LLM performance. Real data exists only after `real_smoke` is run.

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
  outcomes.py      outcome/failure categories + success_rate
  providers.py     provider interface (text chunks + final Usage, ProviderFailure); DummyProvider with simulated tokenizer, output cap, deterministic failures
  openai_provider.py  OpenAI Responses API adapter (urllib, SSE → chunks + Usage, error mapping)
  benchmark.py     run_attempt (price, measure, save) + print_summary, shared by CLI and real_smoke
  real_smoke.py    explicit one-paid-request command
  latency.py       METRICS catalogue (label, unit); measure_request: outcome + token facts + metrics in one pass
  pricing.py       all prices (USD per 1M tokens) + PRICE_PROVENANCE + request_cost
  storage.py       SQLite init + transactional versioned upgrade; save_request; time-window reads; request reads; count_outcomes; spend_by_model
  seed_history.py  deterministic simulated TTFT history + seed command
  dashboard.py     aggregate (/), recent requests (/requests), Benchmark API Spend (/spend); http.server on 127.0.0.1
  percentiles.py   nearest-rank percentile (no HTML)
  config.py        environment, DB path, dashboard port
  __main__.py      CLI
tests/             automated tests
prompts/           prompt history and guidance
design-questions/  interview-style design questions per step
data/              runtime DB; git-ignored
```

Flow: `environment → provider → measure_request (one stream → attempt with outcome + metrics) → price_for (+ request_cost on success) → print → save_request (attempt + observations, one transaction)`; dashboard: `GET /?window=&metric= → parse_query → window_bounds(now) → load_observations(metric, start, end) → render HTML/SVG`.

SQLite (schema version 3, `PRAGMA user_version`; older databases upgrade in place, transactionally, keeping all rows):
- `requests` (one row per attempt): `id` (UUID hex), `recorded_at`, `environment`, `provider`, `model`, `outcome`, `input_tokens`, `requested_max_output_tokens`, `output_tokens`, `input_price_per_1m`, `output_price_per_1m`, `input_cost`, `output_cost`, `total_cost` (USD, unrounded), `failed_after_ms`. A CHECK enforces: success → tokens/costs known, `failed_after_ms` NULL; failure → tokens/costs NULL, `failed_after_ms` set.
- `observations`: `id`, `recorded_at` (UTC), `environment`, `provider`, `model`, `metric`, `value` (unit fixed by `metric`), `request_id` (NULL for pre-Step-010 and seeded rows).
A unique index on observations (`recorded_at`, `environment`, `provider`, `model`, `metric`) lets seeding skip existing rows.

`LLM_METRICS_DB_PATH` can override the default DB path; tests use temporary databases. SQL values are parameterized.

## Known limitations

- Real provider: one model only; price unverified against the official page; smoke call not yet run; `real_smoke` uses a fixed prompt and cap 64. If `gpt-6-luna` spends output tokens on reasoning, 64 may be reached before visible text (recorded honestly, possibly as `invalid_response` if no text arrives).
- Spend covers successful calls' known costs; providers may bill some failed calls, which stay unknown. Cached-input or reasoning-token price differences are not modelled (all input at the standard rate; reasoning tokens are included in OpenAI's output count).
- Simulated provider only; one request per run, with a fixed prompt and `MAX_OUTPUT_TOKENS = 64`.
- Token counts come from a simulated tokenizer (1 token per 4 characters) and prices are simulated; neither matches a real provider.
- No token throughput (`output_tokens_per_s`): the provider gives no per-token timing.
- Observations recorded before Step 010 and seeded history have no request details and are not counted as attempts.
- No retries, no measurement-level timeout (a hung stream would block), and no real-provider error mapping yet; failures are simulated only.
- Partial measurements of failed attempts (e.g. TTFT before a mid-stream failure) are discarded.
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
