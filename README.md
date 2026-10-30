# llm-metrics

An open-source project to independently measure LLM provider performance
(time to first token, throughput, latency, reliability, price).

It is being built in small, tested steps. **Current step: 010.**

> **Simulated data only.** The current implementation uses a dummy provider that
> sleeps for a fixed time and then emits fake tokens. Its numbers do **not**
> represent real LLM performance. No real LLM provider is called.

## What it measures (so far)

Each benchmark run makes one streamed request (one provider call, stream fully
consumed) and records it as a **request** with three metrics, token counts, and
cost.

Metrics (saved as separate observations linked to the request):

| Metric | Name | Unit | Meaning |
|---|---|---|---|
| Total response latency | `total_latency` | ms | Request start → stream fully consumed. The primary latency. |
| Time To First Token | `ttft` | ms | Request start → first text item received. Streaming diagnostic. |
| Output throughput | `output_chunks_per_s` | chunks/s | Output rate after the first chunk: (chunks − 1) ÷ (last chunk time − first chunk time). |

A **chunk** is one non-empty item yielded by the provider's stream. For the
simulated provider each chunk is one fake token; chunks are **not** API or
tokenizer token counts. Throughput excludes the wait for the first chunk, so it
measures generation speed independently of TTFT. It is not recorded when it is
undefined (fewer than two non-empty chunks, or no time between them).

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

Requires Python 3.10+. There are no third-party dependencies.

```bash
git clone https://github.com/akuchlous/llm-metrics.git
cd llm-metrics
./run.sh
```

`./run.sh` creates a `.venv` virtual environment on first run (and reuses it
afterwards), runs all tests, and only if they pass: adds the simulated history
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
Total latency: 181.1 ms
TTFT: 100.2 ms
Output throughput: 49.5 chunks/s
Input tokens: 3 (simulated)
Output tokens: 7 of max 64 (simulated)
Cost: $0.000062 (input $0.000006 + output $0.000056) (simulated)
Saved request 611fc41fb1fb411391b0e71881682ef3 with 3 observations to data/llm_metrics.db

Dashboard: http://127.0.0.1:8000/  (Ctrl+C to stop)
```

If any test fails, the test output is shown and nothing else runs.

## Dashboard

Open the printed URL in a browser. There are two views, both labelled
**TEST / SIMULATED DATA**:

- **Aggregate** (`/`): links to choose a metric (**Total latency**, **TTFT**, or
  **Output throughput**; default TTFT) and a time window (**24h**, **7d**,
  **30d**; default **7d**), and for the selected metric and window: the
  observation count, the latest value, p50/p95/p99, and a line chart over time,
  all in that metric's unit (ms or chunks/s).
- **Recent requests** (`/requests`): the 20 most recent individual requests,
  newest first, with time, request id, total latency, TTFT, chunk throughput,
  input/output/max tokens, and total/input/output cost. Requests recorded
  before Step 010 have no request details and are not listed.

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

The dashboard uses only the Python standard library, has no JavaScript, and
listens on `127.0.0.1` only, so it is not reachable from other machines. On a
Chromebook, open the printed URL in Chrome; if it does not load, try
`http://localhost:8000/`. Stop it with Ctrl+C. If port 8000 is busy, use another:
`LLM_METRICS_PORT=8001 ./run.sh`.

## Manual commands (for development and debugging)

From the repository root:

```bash
python3 -m venv --without-pip .venv   # no dependencies, so no pip needed
source .venv/bin/activate
python -m unittest -v               # run the tests
APP_ENV=test python -m llm_metrics  # run the dummy measurement
python -m llm_metrics.dashboard     # serve the dashboard only
```

## Stored observations

Every successful measurement is appended to a local SQLite database at
`data/llm_metrics.db` (inside the repository folder, git-ignored). The database
and its tables are created automatically on first use; there is nothing to set up.

- **`requests`**: one row per measured request: `id` (llm-metrics' own UUID),
  `recorded_at`, `environment`, `provider`, `model`, `input_tokens`,
  `requested_max_output_tokens`, `output_tokens`, `input_price_per_1m`,
  `output_price_per_1m`, `input_cost`, `output_cost`, `total_cost` (USD).
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
`observations.request_id` (schema version 2). Older rows are not given invented
token, cost, or request data.

To start over, delete the `data/` folder.

Tests never touch this file; they use temporary databases. Setting
`LLM_METRICS_DB_PATH` points the CLI at a different database file.

## Environments

`APP_ENV` selects the environment:

| `APP_ENV`       | Behavior                                                  |
|-----------------|-----------------------------------------------------------|
| `test` (default)| Uses the dummy provider. Never calls a real LLM.          |
| `prod`          | Not supported yet. Exits with an error and measures nothing. |
| anything else   | Exits with an error.                                      |

Never commit secrets. `.env` is git-ignored.
