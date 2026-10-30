# Project direction log

Concise context not captured by `PROJECT_STATUS.md` or `DECISIONS.md`. Keep only decisions and learning that affect future work; this is not a conversation transcript.

_Last updated: 2026-10-30_

## Product direction

`llmxchange` is planned as four independently useful projects:
1. **LLM Metrics** — independent provider/model performance measurements.
2. **LLM Quality Bench** — standardized quality tests and scoring.
3. **LLM Router** — route using performance, quality, price, and constraints.
4. **LLM Exchange** — later add bids/asks, capacity, deadlines, and async jobs.

Build useful measurement data first, then quality, routing, and exchange mechanics. LLM Metrics can itself become a useful public product by periodically publishing provider/model latency, throughput, token usage, cost, errors/availability, and distributions. Individual benchmark calls may also be published so aggregate claims are auditable.

Future real benchmarking needs deliberate dimensions: provider/model, workload category, input size, requested output size, actual output size, and measurement origin (cloud/region/zone). Performance claims are meaningful only for a defined population and methodology.

### Longer-term analytics / exchange metrics

Keep the implementation small now, but preserve an architecture that can grow toward multidimensional provider analytics. Useful dimensions/facts include provider, model, variant/quantization, timestamp/time-of-day, measurement cloud/region/zone, workload/category, input tokens/context length, requested maximum output tokens, actual output tokens, cached input tokens, reasoning tokens, finish reason, and later reproducibly defined workload complexity/classifiers.

Useful measurements include TTFT, total latency, generation tokens/sec, end-to-end effective output tokens/sec, request cost, success/error, error/rate-limit type, retry/fallback count, and availability. Public views can emphasize total latency, cost, token counts, throughput, and reliability while retaining TTFT as an advanced/diagnostic metric.

For the eventual Exchange, request constraints may include maximum price, latency/deadline, minimum throughput, model/workload requirements, and other buyer constraints. Fulfillment facts may later include bid/ask price, selected provider, actual settlement/fulfillment price, retries/fallbacks, and capacity. Do not implement these speculative fields until a concrete step needs them.

Design principle: **dimensions describe the conditions under which a request was measured; metrics describe what happened.** Keep request identity and request-level facts separate from extensible measurements so later analytics can filter coherent populations without turning every dimension into a metric row.

OpenRouter is a useful product reference: its provider/analytics surfaces emphasize latency/TTFT, throughput, uptime/error behavior, token usage (including prompt/completion/reasoning/cached tokens), spend/cost, context length, provider/model/origin dimensions, and routing based on realized price/performance/reliability. llmxchange should retain comparable core facts from the start where practical, then differentiate with controlled benchmark methodology, origin/workload dimensions, and eventual market/fulfillment constraints.

## Development and learning workflow

- GitHub is the source of truth.
- Claude implements one small numbered step; ChatGPT reviews actual code and design material before the next step.
- Material issues get a corrective step before new functionality.
- Used prompts are immutable history.
- Each step writes `prompts/NNN-output.md` and follows `prompts/DESIGN_QUESTIONS.md` for role-specific learning material.
- Implementation drives learning: after review, discuss one or two questions grounded in the completed step.
- Whenever ChatGPT creates a numbered prompt, update this file in the same workflow.

## Implementation progression

`./run.sh` remains the one-command local developer contract.

- Steps 001–006 — dummy TTFT, local run, SQLite persistence, deterministic history, dashboard, nearest-rank p50/p95/p99: complete and reviewed.
- Step 007 — 24h/7d/30d time windows: complete and reviewed.
- Step 008 — TTFT + total response latency from one streamed request, atomic persistence, dashboard metric selector: complete and reviewed.
- Step 009 — output chunk throughput plus metric units and schema versioning: complete and reviewed.
- Step 010 — token accounting, requested-vs-actual output size, per-request cost, request identity, and individual-call view: complete and reviewed; 99 tests reported passing.
- Step 011 — errors, normalized failure categories, persisted failed attempts, and observed benchmark success/failure rate: prompt created.
- Planned after Step 011: first real provider/model.

The aggregate dashboard should answer: **How is this provider/model performing, and is performance changing?** The individual-call view should answer: **What exactly happened on this benchmark request, how much work did it do, how long did it take, what did it cost, and did it succeed?** Simulated data must always be clearly labeled.

## Key design learning

### Raw observations and derived statistics

Keep raw measurements/facts as the source of truth. Percentiles and costs are derived views/facts whose inputs should remain available. Materialize summaries only when scale/performance justifies it. Percentiles are generally not composable; at scale retain raw data or mergeable distribution summaries rather than only precomputed percentile values.

### Define the population before the statistic

The chart and summary statistics must use the same observation population. Eventually a coherent population includes provider/model + origin + workload + request sizes + time window. More samples do not make a mixed population meaningful.

### Measurement methodology

"Fastest provider" is not a provider property in isolation. Observed performance depends on origin, workload, request characteristics, network path, connection setup, time, and timer boundaries. Measurement methodology must match the workload being represented.

For user-facing API performance, total completion latency is usually the intuitive primary metric. TTFT remains useful for streaming responsiveness and diagnostics but should not require public users to understand LLM internals. TTFT also does not isolate provider compute from DNS/TCP/TLS/queueing/prefill when those occur inside the measured boundary.

Reliability has a separate population rule: all attempted benchmark calls belong in observed success/failure rate, while successful latency/throughput distributions must not be polluted with fabricated zero values for failures. "Observed benchmark success rate" is more precise than claiming universal provider uptime because measurements represent the runner's own conditions.

## Step 007–010 review

Step 007 correctly pushed time filtering into parameterized SQLite queries rather than loading all observations into the dashboard. Windows use explicit inclusive UTC bounds relative to current time; invalid/repeated choices are rejected.

Step 008 review result: **pass; no corrective step required.** One provider stream records TTFT and total latency from the same monotonic start and saves them atomically. Total latency depends strongly on output size, so it cannot fairly compare providers that generate different amounts of output.

Step 009 review result: **pass; no corrective step required.** `measure_request()` measures TTFT, total latency, and `output_chunks_per_s` in one pass. Throughput deliberately excludes TTFT and uses `(non-empty chunks - 1)/(last - first chunk time)`. The implementation correctly calls this chunks/s rather than tokens/s. It also introduced a metric catalogue with explicit units and schema version 1, renaming the misleading `value_ms` column to generic `value` while preserving existing rows.

Important Step 009 limitation: provider stream chunks are not provider/API tokens. Exact token accounting must come from a provider/token-accounting boundary rather than assuming one chunk equals one token.

Step 010 review result: **pass; no corrective step required.** The implementation cleanly separates request facts from metric observations: schema v2 adds a UUID-keyed `requests` row linked to observations, provider-reported `Usage` supplies token counts rather than chunks, requested output cap is distinct from actual output, pricing is centralized, effective rates are stored with unrounded costs, and old observations remain unpaired rather than receiving fabricated request facts. Request + observations are written transactionally. The implementation report records 99 tests passing on Python 3.11/3.13 and a real v1-to-v2 upgrade preserving 171 prior observations.

Step-010 known limitations are acceptable for this stage: simulated tokenizer/pricing only, no token/sec metric without defensible token timing, float USD costs, and historical pre-010 observations without request details.

## Step 011 direction

Reliability is first-class for the eventual router/exchange. Step 011 should persist failed benchmark attempts rather than silently losing them, normalize failures into a small cross-provider category set (timeout, rate limit, provider/server, transport, invalid response), and derive observed benchmark success/failure rate from all attempts. Unknown token/cost/performance facts on failures must remain unknown rather than becoming zero. Existing successful latency/throughput percentiles continue to use successful measurements only.

Do not add retries yet. One benchmark attempt remains one provider call. Retry/fallback semantics should be designed later when there is a concrete router/provider integration need.