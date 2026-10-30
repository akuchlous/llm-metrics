# Project status

_Last updated: Step 014c — 2026-10-30_

## Current state

**Step 014c complete: analytics separated from view preparation.** New `llm_metrics/analytics.py` returns natural values (floats, ints, aware datetimes, None for unknown) for metric windows, nearest-rank summaries, success rates, recent attempts, and real-only spend; `dashboard.py` keeps query semantics and turns those facts into display text, links, and chart geometry, and no longer reads storage. Direction `web → dashboard → analytics → storage`, enforced by tests. Rendered pages are byte-identical to 014b (D059).

**Step 014b complete: presentation in Jinja templates.** `dashboard.py` no longer builds HTML: it returns view data (formatted values, "—" for unknown, link targets, chart coordinates) and `web.py` renders it with templates in `llm_metrics/templates/`; the stylesheet moved to `llm_metrics/static/dashboard.css`, so the CSP now allows only same-origin stylesheets (`style-src 'self'`, no `'unsafe-inline'`). Visible page content is unchanged apart from removing development step numbers from product copy (D058).

**Step 014a complete: Flask foundation.** The dashboard's HTTP boundary is now a small Flask application (`llm_metrics/web.py`, `create_app()` factory) in place of `http.server`; routes, query validation, page content, and status codes are unchanged. `dashboard.py` is the HTTP-free application/view layer (validation, data loading via `storage`, HTML rendering); HTML stays in Python until 014b moves it to templates. Flask is the first runtime dependency: pinned with hashes in `requirements.txt` and installed by `run.sh` (D056, D057). Nothing outside `web.py` imports Flask.

**Step 013 complete (Metrics v1 data completeness), all four parts.** Successful attempts record `output_tokens_per_s` (provider-reported output tokens over the first-to-last output chunk interval; TTFT excluded; omitted when undefined), and every new attempt records its benchmark case (`workload_id`: `simulated.default.v1` or `smoke.short_text.v2`), where the runner executed (`origin_cloud` / `origin_region` from `LLM_METRICS_ORIGIN_CLOUD` / `LLM_METRICS_ORIGIN_REGION`, default `local` / `unknown`), the requested `cache_policy` (`disabled` for the OpenAI smoke request, which sends `prompt_cache_options: {"mode": "explicit"}` with no breakpoints; `provider_default` for the simulated provider), and provider-reported `cached_input_tokens` (0 = reported zero, NULL = not reported). Schema version 6; historical rows keep workload/origin/cached tokens NULL and cache policy `unknown`. No paid call was made for this step, so the cache control has not yet been exercised against the live API.

**Step 012a complete; the Step 012 live path is validated.** Step 012 added the first real provider (OpenAI `gpt-6-luna`, Responses API, standard library only) behind the existing boundary, callable only via `python -m llm_metrics.real_smoke` (one paid call, key from `OPENAI_API_KEY`, stored as `prod`); Benchmark API Spend page; real and simulated data labelled and separated. Step 012a closes it: price $0.10 / $0.50 per 1M verified against OpenAI's official pricing documentation; `reasoning.effort: none` confirmed by the official model page; OpenAI's `x-request-id` stored per attempt as `provider_request_id` (schema version 4).

Live validation history (owner-run, 2026-10-30; **validation of the path, not benchmark results**): the first real request (`6a39b71e…`) failed as `provider_error` after 5425.6 ms, and three more early attempts were also stored as `provider_error`. Two later `--debug` runs got HTTP 200 followed by an in-stream `error`; once its nested details were read, it showed `insufficient_quota` / `credit_balance_exhausted` (the OpenAI account had no credit). Those two rows were deleted from the local database at the owner's request, and such account errors are now rejected and not recorded. The earlier failures' cause was never captured and is presumed but not confirmed to be the same. After credit was added, one request succeeded (`44c889cb…`): total latency 3880.7 ms, TTFT 3630.3 ms, 17 input / 14 output tokens (max 64), about $0.000009. One sample says nothing about typical performance.

Working:
- `./run.sh` creates/reuses `.venv`, installs the hash-pinned `requirements.txt` when it changed (network needed only then), runs tests, seeds simulated TTFT history (test only, idempotent), makes one benchmark attempt (outcome, tokens, total latency, TTFT, token and chunk throughput, cost; workload `simulated.default.v1`), then serves the dashboard at `http://127.0.0.1:8000/` until Ctrl+C.
- `APP_ENV=test` is the safe default; `APP_ENV=prod ./run.sh` refuses to run (no implicit spend).
- `python -m llm_metrics.real_smoke [--debug]`: exactly one real OpenAI `gpt-6-luna` request (requires `OPENAI_API_KEY`; refuses without it), stored with `environment = 'prod'`, workload `smoke.short_text.v2`, origin, cache policy `disabled`, OpenAI-reported cached input tokens, and OpenAI's request id; `--debug` prints sanitized failure diagnostics (never stored). Request/configuration and account-credit errors are rejected and not recorded.
- Each run saves one `requests` row (attempt) with its `outcome`, `workload_id`, `origin_cloud`, `origin_region`, `cache_policy` (all required) and `cached_input_tokens` (when reported). Success: tokens, max output tokens, prices, costs, and up to four linked observations (`total_latency`, `ttft`, `output_tokens_per_s`, `output_chunks_per_s`), in one transaction. Failure: category, `failed_after_ms`, prices and cap; tokens/costs NULL (unknown); no observations.
- `python3 -m llm_metrics.seed_history` adds 168 hourly simulated TTFT rows (2026-10-23 00:00 to 2026-10-29 23:00 UTC); re-running adds nothing.
- Dashboard (`python -m llm_metrics.web`, Flask on 127.0.0.1, debug mode always off; `/?window=24h|7d|30d&metric=total_latency|ttft|output_tokens_per_s|output_chunks_per_s`): `TEST / SIMULATED DATA` label, metric and window links, observed benchmark success rate over all attempts in the window (count, rate, failures by category; no attempts → no rate), then for successful attempts only: latest value, nearest-rank p50/p95/p99 with `n` (in the metric's unit), and an SVG chart spanning the window, all from the same `test`/dummy/<metric> rows with `now − window <= recorded_at <= now`. Invalid or repeated `window`/`metric` → HTTP 400. Standard library only; no JavaScript.
- Recent requests view (`/requests`): the 20 most recent attempts with outcome (FAILED + category), tokens, total latency (primary), TTFT, token throughput (before chunk throughput), chunk throughput, costs, failed-after time, provider / model, workload, and origin; unknown values shown as "—"; labelled simulated or real.
- Benchmark API Spend (`/spend?window=`, default 30d, real data only): per provider/model successful paid calls, tokens, known total cost, failed attempts (cost unknown), and a grand total.
- Pages are labelled TEST / SIMULATED DATA or REAL PROVIDER DATA; `/requests?data=simulated|real` switches population.
- 242 `unittest` tests (pass on Python 3.13 in the project venv); none reach external networks (two web tests serve on 127.0.0.1). Web routes are tested with Flask's test client; page tests render the real templates.
- One runtime dependency, Flask (with its libraries), used only by `web.py`. Provider network access and secrets are used only by `real_smoke`.
- All Python follows the Google Python Style Guide (D055): `pyink` formatting, isort `google` import order, and Google's `pylintrc` report no findings. These tools are optional development tools, not dependencies.

Data from `./run.sh` is **simulated** and does not represent real LLM performance. Real data exists only after `real_smoke` is run.

## Run

Requires Linux/Chromebook Linux and Python 3.10+.

```bash
git clone https://github.com/akuchlous/llm-metrics.git
cd llm-metrics
./run.sh
```

Tests only: `.venv/bin/python -m unittest -v` (the web tests need the venv's Flask; `./run.sh` creates it).

Seed simulated history by hand (`./run.sh` already does this in test mode): `python3 -m llm_metrics.seed_history`.

`LLM_METRICS_PORT` changes the dashboard port (default `8000`, `0` = any free port).

## Architecture

```text
run.sh             venv -> dependencies -> tests -> seed (test) -> measurement -> dashboard
requirements.txt   Flask and its libraries, pinned with sha256 hashes
scripts/install_requirements.py  hash-checked install; pinned, verified pip zipapp when the venv has no pip
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
  web.py           Flask HTTP boundary: create_app(), routes /, /requests, /spend, render_page (Jinja), status codes, CSP header, serving on 127.0.0.1
  analytics.py     product analytics as natural values: metric windows (successful observations + nearest-rank summary + success rate over all attempts), recent attempts, real-only spend totals
  dashboard.py     query semantics + view preparation: valid values, window names, page populations; formatting, "—"/"unknown", links, chart geometry (*_view / load_*_view); never reads storage
  templates/       Jinja templates: base.html, aggregate.html, requests.html, spend.html, invalid_query.html, partials (_aggregate_nav, _chart, _macros)
  static/          dashboard.css (served at /static/dashboard.css)
  percentiles.py   nearest-rank percentile (no HTML)
  config.py        environment, DB path, dashboard port
  __main__.py      CLI
tests/             automated tests
prompts/           prompt history and guidance
design-questions/  interview-style design questions per step
data/              runtime DB; git-ignored
```

Flow: `environment → provider → measure_request (one stream → attempt with outcome + metrics) → price_for (+ request_cost on success) → print → save_request (attempt + observations, one transaction)`; dashboard: `GET /?window=&metric= → web route (Flask query args) → dashboard.parse_query → dashboard.load_aggregate_view → window_bounds(now) → analytics.load_metric_window (storage.load_observations / count_outcomes → Observation, MetricSummary, success rate) → dashboard.aggregate_view → view data (formatted values, chart coordinates) → web.render_page("aggregate.html") → Jinja (autoescaped HTML/SVG) → response (status, CSP)`.

SQLite (schema version 6, `PRAGMA user_version`; older databases upgrade in place, transactionally, keeping all rows):
- `requests` (one row per attempt): `id` (UUID hex, our identity), `recorded_at`, `environment`, `provider`, `model`, `outcome`, `input_tokens`, `requested_max_output_tokens`, `output_tokens`, `input_price_per_1m`, `output_price_per_1m`, `input_cost`, `output_cost`, `total_cost` (USD, unrounded), `failed_after_ms`, `provider_request_id` (OpenAI `x-request-id`; NULL when unknown), `workload_id`, `origin_cloud`, `origin_region` (required for new attempts; NULL for rows before Step 013), `cache_policy` (`disabled` / `enabled` / `provider_default` / `unknown`, CHECKed; `unknown` for rows before schema version 6), `cached_input_tokens` (provider-reported; NULL = not reported). A CHECK enforces: success → tokens/costs known, `failed_after_ms` NULL; failure → tokens/costs NULL, `failed_after_ms` set.
- `observations`: `id`, `recorded_at` (UTC), `environment`, `provider`, `model`, `metric`, `value` (unit fixed by `metric`), `request_id` (NULL for pre-Step-010 and seeded rows).
A unique index on observations (`recorded_at`, `environment`, `provider`, `model`, `metric`) lets seeding skip existing rows.

`LLM_METRICS_DB_PATH` can override the default DB path; tests use temporary databases. SQL values are parameterized.

## Known limitations

- Real provider: one model, one successful live sample; no benchmark methodology, scheduling, or repeated runs yet. `real_smoke` uses a fixed prompt, cap 64, and `reasoning.effort: none`.
- The four early `provider_error` rows remain as validation history; their cause was not captured (presumed account credit, unconfirmed). They lower the observed real success rate (1 of 5).
- `provider_request_id` is NULL for attempts before Step 012a (not backfilled), simulated runs, connection failures, and failures detected only by measurement (e.g. the stream ended without a final event). It is stored but not shown on the dashboard.
- No whole-project budget guardrail yet (the `$10/day` operating budget is to be enforced when hosting/scheduling arrives); real spend is limited by running `real_smoke` by hand.
- Spend covers successful calls' known costs; providers may bill some failed calls, which stay unknown. Cached-input (10% rate) and cache-write (1.25×) price differences and reasoning-token differences are not modelled (all input at the standard rate; reasoning tokens are included in OpenAI's output count).
- `./run.sh` uses the simulated provider only; one request per run, with a fixed prompt and `MAX_OUTPUT_TOKENS = 64`.
- Token counts come from a simulated tokenizer (1 token per 4 characters) and prices are simulated; neither matches a real provider.
- `output_tokens_per_s` is observed effective throughput: whole-response token count over client-observed chunk timing. It includes first-chunk and reasoning tokens (reads high for very short responses) and is not internal decoding speed. Not backfilled for older attempts (the one real success has no tokens/s value).
- `workload_id` is a free versioned string with no registry; nothing enforces that a version bump accompanies a prompt or cap change.
- Cache: `disabled` for OpenAI rests on the prompt caching guide's documented explicit mode (GPT-5.6 and later); the gpt-6-luna page does not name the field, and it has not been exercised live. If rejected, the smoke run fails with HTTP 400 and records nothing. The smoke prompt (~17 tokens) is far below the 1,024-token caching minimum anyway, so caching could not affect it yet. Cache-write tokens are not stored. Only the metric-observation query has a cache-policy filter; success-rate and spend queries do not yet, and there are no cache comparison views.
- Origin is whatever the runner is configured to say; it is not verified. Rows before Step 013 have no workload or origin, and there are no origin/workload filters or comparison views yet.
- Observations recorded before Step 010 and seeded history have no request details and are not counted as attempts.
- No retries and no overall attempt deadline (OpenAI's 60 s timeout is per socket operation, so a trickling stream can take longer).
- Partial measurements of failed attempts (e.g. TTFT before a mid-stream failure) are discarded.
- Simulated history exists for TTFT only; total latency and throughput have only live measurements.
- Chunk throughput counts stream chunks, not provider tokens; the dummy's chunks are fixed (5 per response), and its token throughput uses the simulated tokenizer.
- Percentiles are reported the same way for every metric; for throughput (higher is better) the low tail (e.g. p5) would be more informative and is not shown.
- Simulated history uses a fixed past week; it moves out of the 24h/7d windows over time (after 2026-11-28 23:00 UTC it is outside all windows).
- Seeded and live dummy rows are both `test`/`dummy`; they are told apart only by timestamp (seeded rows are on the hour, before 2026-10-30).
- Dashboard has three fixed windows only; no custom ranges, provider filters, zoom, tooltips, or auto-refresh (reload the page).
- Within a window, seeded and live rows are still mixed (no source filter).
- Recent-attempt and spend-group rows still cross the analytics boundary as `storage` dicts (natural values, but untyped); view dictionaries are untyped too, so a mistyped key renders as an empty cell rather than failing. The dashboard uses
- A fresh checkout needs network access to PyPI on its first `./run.sh` (and whenever `requirements.txt` changes); there is no offline wheel cache. Tests must run under the project venv.
- Non-GET requests now return 405 (previously 501); HEAD is answered automatically for GET routes.
- With fewer than 100 observations, nearest-rank p99 equals the maximum.
- Printing the page drops the label's background colour (browser print default).
- Migrations are hand-written upgrade steps in `storage._upgrade`; each schema change needs a new version and an upgrade test.
- A storage failure currently surfaces as a traceback after measurement output.
- `.venv` has no pip until a dependency is justified.

## Next step

To be defined by the next numbered prompt after review.

Do not yet add another provider/model, scheduler, repeated benchmark runs, Docker, cloud deployment, PostgreSQL, authentication, price scraping/history, or workload matrices without a numbered prompt.
