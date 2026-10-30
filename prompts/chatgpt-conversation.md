# Project direction log

Concise context not captured by `PROJECT_STATUS.md` or `DECISIONS.md`. Keep only decisions and learning that affect future work; this is not a conversation transcript.

_Last updated: 2026-10-30_

## Product direction

`llmxchange` is planned as four independently useful projects:
1. **LLM Metrics** — independent provider/model performance measurements.
2. **LLM Quality Bench** — standardized quality tests and scoring.
3. **LLM Router** — route using performance, quality, price, and constraints.
4. **LLM Exchange** — later add bids/asks, capacity, deadlines, and async jobs.

Do not start by rebuilding an OpenRouter-style gateway. Build useful measurement data first, then quality, routing, and exchange mechanics.

LLM Metrics can itself become a useful public product: run benchmarks periodically and publish provider/model TTFT, latency, throughput, cost, errors/availability, and distribution statistics.

Future real benchmarking will need deliberate dimensions rather than ad-hoc schema columns: provider/model, workload category, input size, requested output size, and measurement origin (cloud/region/zone). A performance claim is meaningful only for a defined measurement population and methodology.

## Development and learning workflow

- GitHub is the source of truth.
- Claude implements one small numbered step.
- ChatGPT reviews the actual code and Claude's design material before the next step is created.
- Material issues get a corrective step before new functionality.
- Code, docs, and prompts follow the engineering principles in `DECISIONS.md`.
- Used prompts remain immutable history.
- Each Claude step writes `prompts/NNN-output.md` with implementation results, tradeoffs, limitations/review questions, and concise Design Q&A.
- The implementation drives the learning: after review, use one or two relevant Principal/Sr Manager design questions to understand the code and tradeoffs, then move on.
- Whenever ChatGPT creates a new numbered prompt, update this file in the same workflow.

## Implementation progression

The local developer experience remains one command: `./run.sh`.

- Step 001 — dummy provider + TTFT measurement: complete.
- Step 002 — one-command local run: complete.
- Step 003 — SQLite persistence: complete and reviewed.
- Step 004 — deterministic simulated TTFT history: complete and reviewed.
- Step 005 — lightweight local TTFT dashboard: complete and reviewed.
- Step 006 — nearest-rank p50/p95/p99 plus automatic test-mode seeding: complete and reviewed.
- Step 007 — 24h/7d/30d time windows: prompt created; implementation/review pending.
- Planned next: total response latency, throughput/tokens/sec, errors/availability, then first real provider/model.

The dashboard should answer: **How is this provider/model performing, and is performance changing?** Simulated data must always be clearly labeled.

## Key design learning through Step 006

### Raw observations and derived statistics

Keep raw measurements as the source of truth. Percentiles are derived views, not observations to store alongside raw TTFT. Materialize summaries later only when scale/performance justifies it.

Nearest-rank p50/p95/p99 is currently appropriate because it is simple, deterministic, and always returns an observed latency. High percentiles require enough samples; with small populations p99 often becomes the maximum.

Percentiles are generally not composable: a 24h p99 cannot be reconstructed by averaging hourly p99 values. At scale, retain raw data or mergeable distribution summaries such as histograms/sketches rather than only precomputed percentile numbers.

### Define the population before the statistic

More samples do not automatically make a percentile more meaningful. Measurements should eventually form a coherent population such as provider/model + origin + workload + request sizes + time window. Mixing regions or workloads can produce a statistically valid calculation that is operationally misleading.

The chart and displayed percentile summary must use the same observation population.

### Measurement methodology

"Fastest provider" is not a provider property in isolation. Observed latency depends on measurement origin, workload, request characteristics, network path, connection setup, time, and the exact timer boundaries.

Advanced metrics should eventually distinguish DNS/TCP/TLS/request/provider/first-token/streaming/last-token effects and document warm-vs-cold methodology. Do not add those dimensions before the experiments require them.

Benchmark scheduling must later consider coordinated omission: a sequential benchmark that waits for a slow request before sending the next request can under-sample slow periods and make tail latency look better than the user experience.

## Step 004–006 implementation notes

Step 004 added a fixed, reproducible simulated week (2026-10-23 through 2026-10-29 UTC), idempotent seeding, and a test-only safety boundary. The unique index used for seed idempotence is convenient now but should not be assumed to be the final production observation identity once repeated/concurrent measurements and workload/origin dimensions exist.

Step 005 added a standard-library local dashboard bound only to `127.0.0.1`, server-rendered SVG, CSP, proportional time axis, empty state, and SQLite-backed observations. No framework or chart dependency was justified.

Step 006 added a pure `percentiles.py` calculation layer and made `./run.sh` perform test-only idempotent seeding before the live measurement. Review result: **pass; no corrective Step 006a required.** Current percentiles intentionally describe the same mixed seeded + live population shown by the chart; they are a consistency/demo feature, not real benchmark statistics.

## Step 007 direction

Step 007 adds selectable **24h / 7d / 30d** TTFT windows. Time filtering should happen at the storage/query boundary rather than loading all history and discarding rows in the dashboard. The selected chart and p50/p95/p99 must use exactly the same filtered observations.

Window semantics are relative to real current UTC time, not the newest database observation. This preserves production metric semantics even though the fixed simulated seed will eventually age out of these windows; demo-data convenience must not distort the production data model or clock semantics.

Do not add workload, region/origin, real-provider, aggregation/sketch, or advanced latency-decomposition schema in Step 007. Those remain later design work.
