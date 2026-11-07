# llm-metrics

An open-source project to independently measure LLM provider performance
(time to first token, throughput, latency, reliability, price).

It is being built in small, tested steps. **Current step: 016.**

> **Simulated by default.** `./run.sh` and everything it starts use a dummy
> provider that sleeps for a fixed time and emits fake tokens; its numbers do
> **not** represent real LLM performance and it never calls a real API. Four
> real providers (OpenAI, Anthropic, Google, xAI; one model each) can be called
> **only** by explicitly running `python -m llm_metrics.real_benchmark` (one
> chosen provider, one request) or `python -m llm_metrics.real_smoke` (OpenAI
> connectivity check) with an API key: see
> [Real provider (one paid request)](#real-provider-one-paid-request) and
> [Four-provider benchmark targets](#four-provider-benchmark-targets).

> **Google Cloud:** the deployed setup (jobs, scheduler, buckets, IAM, costs,
> operations, emergency stop) is documented in [gcloud.md](gcloud.md).

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

- **Workload** (`workload_id`): which versioned workload from the catalogue
  was run (see [Benchmark workloads](#benchmark-workloads)), for example
  `interactive-chat-v1` (the `./run.sh` default) or `smoke.short_text.v2` (the
  real smoke request). The prompt itself is never stored; the id is the link
  back to its definition in `llm_metrics/workloads.py`. Older attempts keep
  their ids (`simulated.default.v1` was the "Say hello." run before Step 015).
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
- **`requested_max_output_tokens`**: the output cap the workload asks for
  (e.g. 300 for `interactive-chat-v1`, 64 for the smoke request). It is a
  maximum, not a target: the model may stop earlier, nothing retries or
  extends a short answer, and the generated length is stored separately as
  `output_tokens`.
- **Cost** in USD: `input_cost = input_tokens × input price per 1M ÷ 1,000,000`,
  `output_cost` likewise, `total_cost = input_cost + output_cost`. The prices used
  are stored with each request, so old costs stay explainable if prices change.
  All prices live in `llm_metrics/pricing.py`.

> **Simulated tokens and prices.** The dummy provider counts tokens with a
> simulated tokenizer (1 token per 4 characters, rounded up) and uses simulated
> prices ($2.00 input / $8.00 output per 1M tokens). Neither matches any real
> provider. The dummy's 5-chunk response is 7 tokens, whatever the workload.

## Benchmark workloads

A latency or throughput number means little without knowing what was asked.
Every attempt therefore runs one **workload** from a small code-defined
catalogue (`llm_metrics/workloads.py`): a fixed prompt and output cap under a
stable versioned id. The six benchmark workloads are **candidate hypotheses**
about which application shapes matter; user research may add, change, or
retire them. They measure performance (latency, throughput, reliability,
cost), not answer quality: nothing is graded.

| Workload id | Category | Represents | Approx. input | Output cap |
|---|---|---|---:|---:|
| `interactive-chat-v1` | interactive_chat | Support chat: system context, conversation history, a question needing a step-by-step explanation | ~2K tokens | 300 |
| `coding-v1` | coding | A small multi-file Python codebase with one buggy function and its failing test; asks for diagnosis, fix, and tests | ~8K tokens | 1000 |
| `rag-v1` | rag | 145 supplied transit documents and a question combining two of them, with citations | ~16K tokens | 500 |
| `summarization-v1` | summarization | Three years of committee minutes (216 sections) and a structured-summary request | ~32K tokens | 1000 |
| `extraction-v1` | extraction | 55 semi-structured shipment notices to classify into a small JSON object | ~4K tokens | 150 |
| `agent-tool-v1` | agent_tool | A catalogue of 66 tools, a log of earlier calls, and a goal; asks for the next tool call as text | ~8K tokens | 300 |

`smoke.short_text.v2` (one short sentence, cap 64) is the real-provider
connectivity check, not a benchmark workload.

- **Deterministic, original content.** Prompts are built from synthetic
  material written for this project (fictional companies, places, and data)
  with plain templates and integer arithmetic: no randomness, dates, files, or
  downloads. Tests pin a SHA-256 of every prompt.
- **Versions.** A workload id names exactly one prompt and cap. If a change
  would make new results not directly comparable (different content,
  instructions, task, or cap), it becomes a new version (`rag-v2`); released
  versions are never edited. Old ids stay valid in stored data.
- **Same content, different token counts.** Every provider gets the same text
  for a workload version. Providers tokenize differently, so each reports its
  own input token count; those differences are recorded as facts, not
  corrected. The "approx. input" column is a design target at about 4
  characters per token, not a count any provider will report.
- **Output cap.** A maximum, not a requested length (see above).

Choose a workload for a simulated run with
`APP_ENV=test .venv/bin/python -m llm_metrics --workload rag-v1`; an unknown id
is refused with the list of valid ids before anything runs. `./run.sh` runs
`interactive-chat-v1`. The real smoke command always runs
`smoke.short_text.v2`.

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
Workload: interactive-chat-v1
Origin: local / unknown
Cache policy: provider_default
Outcome: success
Total latency: 181.1 ms
TTFT: 100.3 ms
Output token throughput: 86.7 tokens/s
Output chunk throughput: 49.6 chunks/s
Input tokens: 1954 (simulated)
Cached input tokens: not reported
Output tokens: 7 of max 300 (simulated)
Cost: $0.003964 (input $0.003908 + output $0.000056) (simulated)
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
APP_ENV=test .venv/bin/python -m llm_metrics  # run the dummy measurement (default workload)
APP_ENV=test .venv/bin/python -m llm_metrics --workload coding-v1  # another workload
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
`real_smoke` and `real_benchmark`).

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
2026-11-01, together with the $0.01 cached-input rate). A typical smoke call costs a few millionths of a
dollar.

Errors are recorded as failed attempts with a category (timeout, rate limited,
provider/server error, network/transport error, invalid response). Request or
configuration errors (bad key, no access to the model, bad parameters, account
out of credit) are reported and **not** recorded.

Never commit secrets. `.env` is git-ignored.

## Four-provider benchmark targets

Step 016 adds one deliberately chosen real model per provider, so the same
canonical workload can be measured across providers with the same pipeline.
Nothing here runs automatically: each paid request needs an explicit command.

> The four-provider benchmark controls workload content, workload version,
> output cap, measurement origin and known request settings. It does not
> establish that the selected models have identical capability, tokenizer
> behavior, internal architecture, reasoning implementation, caching
> implementation or service infrastructure. Results describe **observed
> behavior of these exact provider/model/request-profile combinations under
> this benchmark methodology**, not universal provider performance claims.

| Provider | Model | Request profile | API | Reasoning / thinking | Cache policy | Key variable |
|---|---|---|---|---|---|---|
| OpenAI | `gpt-6-luna` | `openai.gpt-6-luna.v1` | Responses | `reasoning.effort: none` (off) | `disabled` (explicit mode, no breakpoints) | `OPENAI_API_KEY` |
| Anthropic | `claude-haiku-5-5` | `anthropic.claude-haiku-5-5.v1` | Messages | `thinking: disabled` (off; effort not sent) | `provider_default` (no `cache_control` sent) | `ANTHROPIC_API_KEY` |
| Google | `gemini-3.5-flash-lite` | `google.gemini-3.5-flash-lite.v1` | Interactions | `thinking_level: minimal` (lowest; not fully off) | `provider_default` (implicit caching) | `GEMINI_API_KEY` |
| xAI | `grok-4.20-0309-non-reasoning` | `xai.grok-4.20-0309-non-reasoning.v1` | Responses | non-reasoning model (no field sent) | `provider_default` (automatic caching) | `XAI_API_KEY` |

- **Same workload, provider-specific wrapper.** Each provider receives the
  exact workload text as its plain input (Anthropic: one user message), with no
  system prompt, instructions, sampling parameters, or tools added. The output
  cap is carried in the provider's own field (`max_output_tokens`,
  `max_tokens`, or `generation_config.max_output_tokens`).
- **Request profiles.** `llm_metrics/targets.py` defines every request setting
  sent to each provider under a versioned profile id, which is stored with
  every attempt (`requests.request_profile_id`). Any material change gets a
  new profile version, so measurements under different settings never share an
  id. Settings that are not sent are provider defaults and are described as
  such.
- **Different controls, not equivalents.** "Reasoning off" means different
  things per provider: OpenAI and Anthropic turn it off; Gemini Flash-Lite can
  only be set to its minimal level; the xAI model is a non-reasoning variant.
  Only OpenAI's request disables prompt caching; the others use the provider's
  default caching, and any cached tokens they report are recorded and priced
  at the cached rate.
- **TTFT** is measured exactly as before: from just before the request until
  the first text delta. Role, start, ping, thinking-signature and other
  metadata events never count as output.
- **Tokens** come only from each provider's reported usage. The same text
  yields different input counts per provider; that difference is data. Output
  tokens include any billed thinking tokens.
- **Prices** (USD per 1M tokens, standard tier, verified 2026-11-01 against
  official pricing pages): OpenAI 0.10 input / 0.50 output / 0.01 cached;
  Anthropic 0.10 / 0.50 / 0.01 (prompts up to 100K); Google 0.30 / 2.50 / 0.03;
  xAI 1.25 / 2.50 / 0.20 (prompts under 200K). Each attempt stores the rates
  its cost used.

The adapters are small standard-library HTTP clients, one per provider.
LiteLLM was evaluated as a replacement and not adopted because it would change
measured facts (D065).

Run **one** request to **one** provider (the pilot path):

```bash
export ANTHROPIC_API_KEY=...   # only the chosen provider's key is read
python3 -m llm_metrics.real_benchmark --provider anthropic --real
python3 -m llm_metrics.real_benchmark --provider google --real --workload interactive-chat-v1 --debug
```

`--provider` and `--real` are required; there is no "all providers" option,
no loop and no retry. Before the request it prints the provider, model,
profile, endpoint, reasoning setting, cache policy, workload, output cap,
origin and rates; it never prints the key, prompt or response. Missing keys,
unknown providers or workloads, and invalid origins are refused before any
network access. Requests the provider rejects because of our key, access,
parameters or billing are reported and not recorded.


## Offline analytics from GCS records (read-only)

`python -m llm_metrics.record_analytics` turns a **local copy** of the
immutable per-attempt records (`llm-metrics.attempt.v1`) into one versioned
summary file (`llm-metrics.analytics.v1`). It never contacts GCP, OpenAI or a
database, and it does not use the SQL-backed dashboard. Getting the mirror is a
separate, explicit operator action, for example
`gcloud storage cp -r gs://llm-metrics-513617-results/attempts/v1 MIRROR/attempts/`.

Try it on the committed synthetic fixture (not real measurements):

```bash
.venv/bin/python -m llm_metrics.record_analytics \
  --input tests/fixtures/gcs_mirror --output /tmp/summary.json \
  --provider openai --model gpt-6-luna --profile openai.gpt-6-luna.v1 \
  --workload interactive-chat-v1 --origin gcp/us-central1 \
  --start 2026-01-05T18:00:00Z --end 2026-01-05T20:00:00Z \
  --collector-policy-start 2026-01-05T18:00:00Z
```

- **Population:** only `prod` records under `MIRROR/<prefix>/v1/requests/prod/`, matched by exact provider, model, profile, workload and origin, with `start <= recorded_at < end` (UTC). `test` records and the `snapshots/` CSV backups are never read.
- **Semantics:**
  - Reliability counts every selected attempt, failures included.
  - TTFT, total latency and throughput use successful observations only, with nearest-rank p50/p95, min, max and latest. A failure never becomes a 0 latency.
  - Known costs and tokens are summed over successes. Failed attempts are counted as cost-unknown.
- **Slots:** records alone cannot show slots that produced no record. Slot completeness (missing / claim without record) is reported only with `--collector-policy-start`, from the collector's claims in the same mirror; otherwise it is `null`.
- **Evidence:** each record's object name, attempt id, outcome and SHA-256 are listed, plus the SHA-256 of a `sha256sum`-format manifest. No provider request ids, prompts or responses are written.
- **Fail-closed:** malformed, non-canonical, misplaced, oversized or symlinked files, unexpected entries, duplicate provider request ids, mixed populations, inconsistent slot evidence or zero matching records all exit 1 with nothing written. Bad arguments exit 2.
- **Output:** canonical JSON with no wall-clock fields, so identical inputs give byte-identical files. It is written atomically and create-only: an existing file with different content is never replaced, and an identical one is left as is.

## Static question and metric pages (local only)

`python -m llm_metrics.static_site` builds the public website's pages as
plain files: the question article `/how-to-measure-openai-ttft`, the metric
page `/metrics/openai/ttft`, the home page and the `/llm-performance` hub. It
needs no web server, database, GCP or provider. Nothing is hosted or
deployed by this command.

```bash
# Educational pages only: the metric page shows "no validated measurements".
.venv/bin/python -m llm_metrics.static_site --output /tmp/site \
  --site-url https://llmxchange.com --report /tmp/site-report.json

# With a Step 024 summary. The source must be declared; synthetic data is
# bannered and marked noindex on every page.
.venv/bin/python -m llm_metrics.static_site --output /tmp/site \
  --site-url https://llmxchange.com \
  --analytics summary.json --data-source synthetic

# Preview (clean URLs need a server; file:// links will not resolve).
.venv/bin/python -m http.server 8000 --bind 127.0.0.1 -d /tmp/site
```

- **Editorial text** lives in `llm_metrics/site_content/<page>/` as `page.json` (title, description, breadcrumb name, answer revision, dates and authors only when known) plus static HTML fragments checked against a small tag allowlist. **Numbers** are rendered only from a validated `llm-metrics.analytics.v1` file, never into the reviewed answer.
- **Adding an article:** create a new directory with `page.json` and fragments, then list it in `site_content/site.json`. The shared template, metadata, breadcrumbs, JSON-LD and checks apply automatically.
- **Build checks (fail the build):**
  - title, description, canonical and Open Graph tags;
  - one H1 and no skipped heading levels;
  - visible breadcrumbs identical to the `BreadcrumbList`;
  - `Article` URL and headline;
  - every internal link resolves; no executable scripts;
  - question ↔ metric cross-links.
- **Editorial report:** advisory pass/warn/manual findings inspired by Yoast's checks (keyphrase placement, lengths, sentence length, links). It is not a ranking score.

### Questions, dated editions and publishing (Step 026)

Each question in `llm_metrics/site_content/questions/<name>/` has a `question.json` registry entry: a permanent `question_id`, its stable URL, related metric pages and an ordered list of editions. Each edition `editions/eN/` uses the Step 025 `page.json` and fragment format, plus `status` (`draft` or `approved`), a feed `summary`, `what_changed` (every edition after the first), and `source_commit`.

```bash
# Review drafts (noindex, nothing archived):
.venv/bin/python -m llm_metrics.static_site --output /tmp/site \
  --site-url https://llmxchange.com --preview-at 2026-11-08T09:00:00Z

# Publish approved editions: freezes their HTML into site_content/archive/
# (commit it), then builds the site.
.venv/bin/python -m llm_metrics.static_site --output /tmp/site \
  --site-url https://llmxchange.com --publish-at 2026-11-08T09:00:00Z
```

- **Dated editions:** each edition lives at `/reports/<UTC publication date>/<slug>`, and a second edition on the same day gets `/r2`. Once published, the bytes never change: the build serves the archived file and refuses if it, or the edition's source, was modified.
- **Indexes:** the home page lists editions newest first, and `/questions` groups them by question. The stable question page shows the latest answer, its edition history and related metrics.
- **Canonicals:** dated editions are canonical to the stable page.
- **Redirect plan:** the output's `redirects.json` lists `<slug>-latest` → `<slug>` (301) for the hosting step.
- **Indexing:** an empty or synthetic metric page is `noindex`. Educational questions need no dataset and stay indexable.
