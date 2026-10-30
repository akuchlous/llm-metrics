# llm-metrics

An open-source project to independently measure LLM provider performance
(time to first token, throughput, latency, reliability, price).

It is being built in small, tested steps. **Current step: 012.**

> **Simulated by default.** `./run.sh` and everything it starts use a dummy
> provider that sleeps for a fixed time and emits fake tokens; its numbers do
> **not** represent real LLM performance and it never calls a real API. One
> real provider (OpenAI `gpt-6-luna`) can be called **only** by explicitly running
> `python -m llm_metrics.real_smoke` with an API key: see
> [Real provider (one paid request)](#real-provider-one-paid-request).

## What it measures (so far)

Each benchmark run makes one **attempt**: one streamed request (one provider
call, no retries). Every attempt is recorded with its **outcome**, whether it
succeeds or fails. A successful attempt also records three metrics, token
counts, and cost.

Outcomes: `success`, or one of the internal failure categories `timeout`,
`rate_limited`, `provider_error`, `transport_error`, `invalid_response` (e.g.
the stream reported no usage). For a failed attempt, tokens, cost, and
performance are **unknown** (stored empty, never as zero), and `failed_after_ms`
records how long the attempt ran before the failure was detected.

Metrics of a successful attempt (saved as separate observations linked to it):

| Metric | Name | Unit | Meaning |
|---|---|---|---|
| Total response latency | `total_latency` | ms | Request start → stream fully consumed. The primary latency. |
| Time To First Token | `ttft` | ms | Request start → first text item received. Streaming diagnostic. |
| Output token throughput | `output_tokens_per_s` | tokens/s | Provider-reported output tokens ÷ (last chunk time − first chunk time). The preferred throughput. |
| Output chunk throughput | `output_chunks_per_s` | chunks/s | Output rate after the first chunk: (chunks − 1) ÷ (last chunk time − first chunk time). Kept for continuity. |

A **chunk** is one non-empty item yielded by the provider's stream. For the
simulated provider each chunk is one fake token; chunks are **not** API or
tokenizer token counts. Both throughputs exclude the wait for the first chunk,
so they measure generation speed independently of TTFT.

**Token throughput** divides the provider's own output token count (from its
usage report, never the chunk count) by the time between the first and last
output chunk. The token count covers the whole response, while the timing is
what the client saw on the stream, so this is an *observed effective generation
throughput*, not the provider's internal decoding speed. Because tokens in the
first chunk are counted but the wait for that chunk is not, it reads somewhat
high for very short responses. For the simulated provider the tokens come from
the simulated tokenizer.

A throughput is not recorded when it is undefined: fewer than two non-empty
chunks, no time between them, or (tokens/s only) no output tokens reported. It
is never stored as zero or infinity.

Every attempt also records two facts about how it was run:

- **Workload** (`workload_id`): the benchmark case, i.e. what test was run, as a
  stable versioned name. `simulated.default.v1` is the simulated run
  (`./run.sh`); `smoke.short_text.v2` is the real smoke request. A changed
  prompt, cap, or request shape gets a new version.
- **Origin** (`origin_cloud` / `origin_region`): where the benchmark runner
  executed, not where the provider served the request. It is set with
  `LLM_METRICS_ORIGIN_CLOUD` and `LLM_METRICS_ORIGIN_REGION`, for example
  `aws` / `us-east-1`. When unset it is `local` / `unknown`. Values must be
  lowercase letters, digits and inner hyphens (at most 63 characters); anything
  else stops the run before any request. The origin is never guessed from IP
  addresses, geolocation, or cloud metadata services.

Two cache facts are recorded per attempt, because prompt caching can change
TTFT, latency, and cost a lot:

- **Cache policy** (`cache_policy`): what the request asked of the provider's
  prompt cache. `disabled`: a documented provider control for no cache reuse
  was sent (the real smoke request sets OpenAI's explicit cache mode with no
  breakpoints, which per OpenAI's prompt caching guide "does not use prompt
  caching or create cache writes"). `enabled`: cache reuse was explicitly
  requested. `provider_default`: no cache control was sent (the simulated
  provider). `unknown`: attempts recorded before this was tracked.
- **Cached input tokens** (`cached_input_tokens`): the part of the input the
  provider *reports* it read from its cache (OpenAI:
  `usage.input_tokens_details.cached_tokens`). `0` means the provider reported
  zero; empty (—) means it was not reported, which is not the same as zero. It
  is never guessed from latency or repeated prompts.

Terminology: **uncached / cold-ish** means the request disabled caching and/or
the provider reported 0 cached input tokens. It does not mean every internal
provider cache was cold. **cached / warm** means the provider reported cached
input tokens, or the benchmark deliberately enabled caching. Default and
unknown cache states are shown as such, never as cold. Different cache policies
are different populations and should not be combined into one performance
claim.

Timings use `time.perf_counter()` (monotonic, high resolution).

Request facts:

- **`input_tokens`** and **`output_tokens`**: as reported by the provider at the
  end of the stream (never counted from chunks: a chunk may hold zero, one, or
  several tokens).
- **`requested_max_output_tokens`**: the output cap the benchmark asked for
  (64). The model may stop earlier, so it is stored separately from
  `output_tokens`.
- **Cost** in USD: `input_cost = input_tokens × input price per 1M ÷ 1,000,000`,
  `output_cost` likewise, `total_cost = input_cost + output_cost`. The prices used
  are stored with each request, so old costs stay explainable if prices change.
  All prices live in `llm_metrics/pricing.py`.

> **Simulated tokens and prices.** The dummy provider counts tokens with a
> simulated tokenizer (1 token per 4 characters, rounded up) and uses simulated
> prices ($2.00 input / $8.00 output per 1M tokens). Neither matches any real
> provider. The dummy's 5-chunk response is 7 tokens.

## Quick start (Chromebook Linux terminal or any Linux)

Requires Python 3.10+ and, on the first run only, a network connection to
download the pinned dependencies (Flask and its libraries) from PyPI.

```bash
git clone https://github.com/akuchlous/llm-metrics.git
cd llm-metrics
./run.sh
```

`./run.sh` creates a `.venv` virtual environment on first run (and reuses it
afterwards), installs the exact versions in `requirements.txt` into it with
hash checking (again only when that file changes), runs all tests, and only if they pass: adds the simulated history
(test mode only, once), runs the TTFT measurement, and starts the local dashboard:

```
LLM Metrics — local test environment
✓ Python environment ready
✓ Tests passed
Simulated TTFT history: 168 new, 0 already present (2026-10-23 00:00 to 2026-10-29 23:00 UTC, hourly)
Database: data/llm_metrics.db
✓ Simulated history ready
✓ Starting test measurement

Provider: dummy
Model: dummy-model-v1
Workload: simulated.default.v1
Origin: local / unknown
Cache policy: provider_default
Outcome: success
Total latency: 181.1 ms
TTFT: 100.3 ms
Output token throughput: 86.7 tokens/s
Output chunk throughput: 49.6 chunks/s
Input tokens: 3 (simulated)
Cached input tokens: not reported
Output tokens: 7 of max 64 (simulated)
Cost: $0.000062 (input $0.000006 + output $0.000056) (simulated)
Rates: $2.00 input / $8.00 output per 1M tokens (simulated)
Saved attempt 8e5578e2e1024fe6b868f77b1ecfc801 with 4 observations to data/llm_metrics.db

Dashboard: http://127.0.0.1:8000/  (Ctrl+C to stop)
```

If any test fails, the test output is shown and nothing else runs.

## Dashboard

Open the printed URL in a browser. Every page is labelled with its data:
**TEST / SIMULATED DATA** (orange) or **REAL PROVIDER DATA** (blue). The two
are never mixed on one page.

- **Aggregate** (`/`): links to choose a metric (**Total latency**, **TTFT**,
  **Output token throughput**, or **Output chunk throughput**; default TTFT) and a time window (**24h**, **7d**,
  **30d**; default **7d**). For the window it shows the **observed benchmark
  success rate**: successes ÷ all attempts, with the attempt count and failures
  by category (no attempts → no rate). This is what our runner observed, not a
  provider's overall uptime. Below it, for the selected metric and **successful
  attempts only**: the observation count, the latest value, p50/p95/p99, and a
  line chart over time, all in that metric's unit (ms, tokens/s, or chunks/s).
- **Recent requests** (`/requests?data=simulated|real`, default simulated): the
  20 most recent attempts of that data, newest first,
  with time, attempt id, outcome (success or FAILED with its category), total
  latency, TTFT, token throughput, chunk throughput, input/output/max tokens,
  total/input/output cost, for failures the time until the failure, provider /
  model, workload, origin, cache policy, and cached input tokens. Unknown values show as
  "—". Measurements recorded before Step 010 have no attempt details and are
  not listed.
- **Benchmark API Spend** (`/spend`, real data only): for a time window (default
  **30d**), per provider and model: successful paid calls, input and output
  tokens, and total cost; failed attempts are counted with their cost
  **unknown** (never $0); plus a grand total. This is the API token cost
  incurred by llm-metrics to run its own benchmark requests, **not** the
  provider's revenue, what every user pays, hosting or infrastructure cost, or a
  workload-independent price comparison.

Windows end at the current UTC time: `/?window=24h&metric=total_latency` shows
total-latency observations with `now − 24h <= recorded_at <= now` (both ends
inclusive). Everything on the page is computed from that same set of
observations. Any other, empty, or repeated `window` or `metric` value returns an
error page listing the valid choices. The seeded history is a fixed week
(2026-10-23 to 2026-10-29) of TTFT only, so as time passes it moves out of the
shorter windows, and total latency and throughput have only live measurements;
that is expected.

Percentiles use the **nearest-rank** method over the selected window's
observations (the same ones as the chart): sort the values and take the one at rank ⌈p × n / 100⌉. The result is
always a real observed value; with fewer than 100 observations, p99 equals the
maximum.

The dashboard is a small Flask application with server-rendered pages (Jinja
templates in `llm_metrics/templates/`, one stylesheet in `llm_metrics/static/`)
and no JavaScript. Its code is layered so each concern has one owner: `web.py`
(HTTP, template rendering, JSON encoding) → `dashboard.py` (how values are
worded for people) or `api.py` (how they are represented for programs) →
`analytics.py` (statistics over stored facts, as plain numbers and times) →
`storage.py` (SQLite). `query.py` holds what both may select: metrics and
their units, windows, and populations. It listens on `127.0.0.1` only, so it is not reachable from other
machines, and never runs in Flask debug mode. On a
Chromebook, open the printed URL in Chrome; if it does not load, try
`http://localhost:8000/`. Stop it with Ctrl+C. If port 8000 is busy, use another:
`LLM_METRICS_PORT=8001 ./run.sh`.

## JSON API (v1, read-only)

`GET /api/v1/metrics?metric=<name>&window=24h|7d|30d` returns the aggregate
page's data as JSON facts for programs. It accepts the same metric and window
values, with the same defaults (`ttft`, `7d`), and computes nothing of its own:
both the page and the API read the same analytics result.

```bash
curl -s 'http://127.0.0.1:8000/api/v1/metrics?metric=ttft&window=24h'
```

```json
{
  "api_version": "v1",
  "population": {"data": "simulated", "provider": "dummy", "model": "dummy-model-v1"},
  "metric": {"name": "ttft", "unit": "ms"},
  "window": {"name": "24h", "start": "2026-10-29T12:00:00.000000Z", "end": "2026-10-30T12:00:00.000000Z"},
  "samples": {
    "count": 25,
    "first_recorded_at": "2026-10-29T13:00:00.000000Z",
    "latest": {"recorded_at": "2026-10-30T11:58:02.123456Z", "value": 100.4},
    "percentiles": {"p50": 100.3, "p95": 104.5, "p99": 111.6}
  },
  "reliability": {
    "attempts": 12, "successes": 12, "failures": 0,
    "success_rate": 1.0, "failure_rate": 0.0,
    "failures_by_category": {"timeout": 0, "rate_limited": 0, "provider_error": 0, "transport_error": 0, "invalid_response": 0}
  }
}
```

| Field | Type | Meaning |
|---|---|---|
| `api_version` | string | Always `"v1"` on this path. |
| `population.data` | string | `"simulated"` (dummy provider; not real LLM performance). The only population for now. |
| `population.provider`, `.model` | string | The measured provider and model. |
| `metric.name`, `.unit` | string | The selected metric and the unit of every value below (`ms`, `tokens/s`, or `chunks/s`). |
| `window.name` | string | `24h`, `7d`, or `30d`. |
| `window.start`, `.end` | string | Inclusive bounds; `end` is the request time. |
| `samples.count` | integer | Successful observations of this metric in the window (failures never contribute values). |
| `samples.first_recorded_at` | string or null | Time of the oldest one. |
| `samples.latest` | object or null | The newest observation: `recorded_at` and `value`. |
| `samples.percentiles` | object or null | `p50`, `p95`, `p99` by nearest rank over those observations. |
| `reliability.attempts`, `.successes`, `.failures` | integer | Every benchmark attempt of the population in the window, successful or failed. |
| `reliability.success_rate`, `.failure_rate` | number or null | Fractions 0–1; `null` when there were no attempts. |
| `reliability.failures_by_category` | object | Attempts per failure category (every category present). |

- **Times** are ISO 8601 UTC with microseconds and a `Z` suffix.
- **`null`** means no such fact exists in the window (no observations, or no
  attempts); it is never written as 0. A valid but empty window is still
  `200`.
- **Samples vs attempts:** `samples` and `reliability` are different
  populations on purpose. A failure counts in `reliability` but adds no
  sample, and seeded simulated history has observations without attempt
  records, so `samples.count` can exceed `reliability.attempts`.
- **Errors** are JSON too: an unknown, empty, or repeated `metric`/`window`
  returns `400` with `{"api_version": "v1", "error": {"code":
  "invalid_query", "message": …, "valid": …, "defaults": …}}`, never echoing
  the submitted value. Unknown paths under `/api/` return `404`
  (`not_found`), other methods `405` (`method_not_allowed`), and server
  errors `500` (`internal_server_error`) without details.
- **Compatibility:** once relied on, v1 field names, meanings, units, and
  types do not change. New fields may be added, so ignore fields you do not
  know; renaming, removing, or retyping a field would need `/api/v2/`.

No authentication or CORS: like the dashboard, the API is served on
`127.0.0.1` only.

## Manual commands (for development and debugging)

From the repository root:

```bash
./run.sh                                  # first time: creates .venv, installs dependencies
.venv/bin/python -m unittest -v           # run the tests (needs the venv's Flask)
APP_ENV=test .venv/bin/python -m llm_metrics  # run the dummy measurement
.venv/bin/python -m llm_metrics.web       # serve the dashboard only
```

Dependencies are pinned with hashes in `requirements.txt` and installed by
`scripts/install_requirements.py`, which works even though the venv has no pip:
it downloads pip's official single-file release at a pinned version and checks
its hash before using it. Only Flask and its own libraries are installed;
benchmarking, storage, and analytics use the standard library only.

## Stored observations

Every successful measurement is appended to a local SQLite database at
`data/llm_metrics.db` (inside the repository folder, git-ignored). The database
and its tables are created automatically on first use; there is nothing to set up.

- **`requests`**: one row per benchmark attempt: `id` (llm-metrics' own UUID),
  `recorded_at`, `environment`, `provider`, `model`, `outcome`, `input_tokens`,
  `requested_max_output_tokens`, `output_tokens`, `input_price_per_1m`,
  `output_price_per_1m`, `input_cost`, `output_cost`, `total_cost` (USD), and
  `failed_after_ms`. For failed attempts the token and cost columns are empty
  (NULL = unknown).
- **`observations`**: one row per metric value: `id`, `recorded_at` (UTC, e.g.
  `2026-10-30T00:43:46.279219Z`), `environment` (`test` or `prod`), `provider`,
  `model`, `metric`, `value` (in the metric's unit), and `request_id` (the
  request it belongs to; empty for rows recorded before Step 010 and for
  simulated history).

Rows with `environment = 'test'` come from the dummy provider and are simulated.

To look at the data (uses only Python):

```bash
python3 -c "import sqlite3; [print(r) for r in sqlite3.connect('data/llm_metrics.db').execute('SELECT * FROM observations')]"
python3 -c "import sqlite3; [print(r) for r in sqlite3.connect('data/llm_metrics.db').execute('SELECT * FROM requests')]"
```

### Simulated history

`./run.sh` adds a week of simulated hourly TTFT history automatically in test
mode. To add it by hand:

```bash
python3 -m llm_metrics.seed_history
```

This inserts 168 deterministic observations, one per hour from
2026-10-23 00:00 to 2026-10-29 23:00 UTC, labelled `environment = 'test'`.
Running it again adds nothing. It refuses to run with `APP_ENV=prod`, and
`./run.sh` never seeds in `prod`.

Older databases are upgraded automatically in place, in one transaction, and
existing rows are kept: Step 009 renamed the `value_ms` column to `value`
(schema version 1); Step 010 added the `requests` table and
`observations.request_id` (schema version 2); Step 011 added `outcome` and
`failed_after_ms` and made token/cost columns nullable (schema version 3), with
Step-010 requests recorded as successes; Step 012a added
`requests.provider_request_id` (schema version 4), NULL for existing rows;
Step 013 added `workload_id`, `origin_cloud` and `origin_region` (schema version
5), NULL (unknown) for existing rows because they were never recorded; Step 013
also added `cache_policy` (set to `unknown` for existing rows) and
`cached_input_tokens` (NULL) (schema version 6).
Older rows are not given invented token, cost, or request data.

To start over, delete the `data/` folder.

Tests never touch this file; they use temporary databases. Setting
`LLM_METRICS_DB_PATH` points the CLI at a different database file.

## Environments

`APP_ENV` selects the environment:

| `APP_ENV`       | Behavior                                                  |
|-----------------|-----------------------------------------------------------|
| `test` (default)| Uses the dummy provider. Never calls a real LLM.          |
| `prod`          | `./run.sh` / `python -m llm_metrics` refuse and measure nothing (no implicit spend). |
| anything else   | Exits with an error.                                      |

Stored data uses `environment = 'test'` for simulated attempts and
`environment = 'prod'` for real-provider attempts (written only by
`real_smoke`).

## Real provider (one paid request)

The only code that calls a paid API, and only when you run it:

```bash
export OPENAI_API_KEY=...    # your key; never commit it or put it in a file in this repo
python3 -m llm_metrics.real_smoke
```

It prints what it is about to do, then makes **exactly one** OpenAI Responses API
call (`gpt-6-luna`, a fixed harmless one-sentence prompt, `max_output_tokens` 64,
`reasoning.effort` `none`, prompt caching disabled via
`prompt_cache_options: {"mode": "explicit"}` with no breakpoints, streaming, no
tools, `store: false`, no retries),
saves the attempt as real data,
and prints the outcome, tokens, latencies, throughput, cost, the rates used, and
OpenAI's request id (`x-request-id`). That id is stored with the attempt next to
llm-metrics' own request id, so a specific benchmark request can be raised with
OpenAI. `reasoning.effort` `none` is set explicitly (the model's default is
`medium`) so the benchmark measures plain text generation.
It never prints the key, the prompt, or the response. Without `OPENAI_API_KEY`
it refuses and makes no request.

Add `--debug` to print sanitized diagnostics to the terminal when the attempt
fails or is rejected: which code path failed, the HTTP status, OpenAI's
`x-request-id`, and OpenAI's error code/type/param or incomplete reason. These
are never stored and never include the key, prompt, response text, headers, or
provider error messages:

```bash
python3 -m llm_metrics.real_smoke --debug
```

Token counts come from OpenAI's reported usage. Cost uses the standard-tier
price in `llm_metrics/pricing.py`: **$0.10 per 1M input tokens and $0.50 per
1M output tokens** (source: OpenAI's official pricing documentation,
https://developers.openai.com/api/docs/pricing, standard tier; verified on
2026-10-30). A typical smoke call costs a few millionths of a
dollar.

Errors are recorded as failed attempts with a category (timeout, rate limited,
provider/server error, network/transport error, invalid response). Request or
configuration errors (bad key, no access to the model, bad parameters, account
out of credit) are reported and **not** recorded.

Never commit secrets. `.env` is git-ignored.
