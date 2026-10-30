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
- Step 010 — token accounting, requested-vs-actual output size, per-request cost, request identity, and individual-call view: prompt created; implementation pending.
- Planned after Step 010: errors/availability, then first real provider/model.

The aggregate dashboard should answer: **How is this provider/model performing, and is performance changing?** The individual-call view should answer: **What exactly happened on this benchmark request, how much work did it do, how long did it take, and what did it cost?** Simulated data must always be clearly labeled.

## Key design learning

### Raw observations and derived statistics

Keep raw measurements/facts as the source of truth. Percentiles and costs are derived views/facts whose inputs should remain available. Materialize summaries only when scale/performance justifies it. Percentiles are generally not composable; at scale retain raw data or mergeable distribution summaries rather than only precomputed percentile values.

### Define the population before the statistic

The chart and summary statistics must use the same observation population. Eventually a coherent population includes provider/model + origin + workload + request sizes + time window. More samples do not make a mixed population meaningful.

### Measurement methodology

"Fastest provider" is not a provider property in isolation. Observed performance depends on origin, workload, request characteristics, network path, connection setup, time, and timer boundaries. Measurement methodology must match the workload being represented.

For user-facing API performance, total completion latency is usually the intuitive primary metric. TTFT remains useful for streaming responsiveness and diagnostics but should not require public users to understand LLM internals. TTFT also does not isolate provider compute from DNS/TCP/TLS/queueing/prefill when those occur inside the measured boundary.

## Step 007–009 review

Step 007 correctly pushed time filtering into parameterized SQLite queries rather than loading all observations into the dashboard. Windows use explicit inclusive UTC bounds relative to current time; invalid/repeated choices are rejected.

Step 008 review result: **pass; no corrective step required.** One provider stream records TTFT and total latency from the same monotonic start and saves them atomically. Total latency depends strongly on output size, so it cannot fairly compare providers that generate different amounts of output.

Step 009 review result: **pass; no corrective step required.** `measure_request()` measures TTFT, total latency, and `output_chunks_per_s` in one pass. Throughput deliberately excludes TTFT and uses `(non-empty chunks - 1)/(last - first chunk time)`. The implementation correctly calls this chunks/s rather than tokens/s. It also introduced a metric catalogue with explicit units and schema version 1, renaming the misleading `value_ms` column to generic `value` while preserving existing rows.

Important Step 009 limitation: provider stream chunks are not provider/API tokens. Exact token accounting must come from a provider/token-accounting boundary rather than assuming one chunk equals one token.

## Step 010 direction

Cost and workload size are first-class product metrics. Step 010 adds explicit input-token count, requested maximum output tokens, actual output-token count, pricing basis, and per-request input/output/total cost while remaining simulated.

The same text may tokenize differently across models, so future comparisons must distinguish "same text" from "same token count." Likewise, a requested output cap is not the same as actual generated output: both should be retained.

Step 010 also introduces an explicit llm-metrics request identity because timestamp-only pairing is too weak once request-level facts and future concurrency matter. Historical pre-Step-010 observations should remain valid without fabricating missing token/cost/request data.

Pricing can change. Preserve the effective pricing basis used for an individual request so historical cost remains explainable; do not build a full pricing-history service yet.

The eventual public product may expose individual benchmark calls containing provider/model, timestamp, input/output token counts, requested output limit, total latency, diagnostic TTFT, throughput, cost, and later origin/workload metadata. This provides auditability underneath aggregate provider comparisons.
