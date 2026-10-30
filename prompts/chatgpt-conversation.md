# Project direction log

Concise context not captured by `PROJECT_STATUS.md` or `DECISIONS.md`. Keep only decisions and learning that affect future work; this is not a conversation transcript.

_Last updated: 2026-10-30_

## Product direction

`llmxchange` is planned as four independently useful projects:
1. **LLM Metrics** — independent provider/model performance measurements.
2. **LLM Quality Bench** — standardized quality tests and scoring.
3. **LLM Router** — route using performance, quality, price, and constraints.
4. **LLM Exchange** — later add bids/asks, capacity, deadlines, and async jobs.

Build useful measurement data first, then quality, routing, and exchange mechanics. LLM Metrics can itself become a useful public product by periodically publishing provider/model TTFT, completion latency, throughput, cost, errors/availability, and distributions.

Future real benchmarking needs deliberate dimensions: provider/model, workload category, input size, requested output size, and measurement origin (cloud/region/zone). Performance claims are meaningful only for a defined population and methodology.

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
- Step 009 — output throughput: prompt created; implementation pending.
- Planned next: errors/availability, then first real provider/model.

The dashboard should answer: **How is this provider/model performing, and is performance changing?** Simulated data must always be clearly labeled.

## Key design learning

### Raw observations and derived statistics

Keep raw measurements as the source of truth. Percentiles are derived views. Materialize summaries only when scale/performance justifies it. Percentiles are generally not composable; at scale retain raw data or mergeable distribution summaries rather than only precomputed percentile values.

### Define the population before the statistic

The chart and summary statistics must use the same observation population. Eventually a coherent population includes provider/model + origin + workload + request sizes + time window. More samples do not make a mixed population meaningful.

### Measurement methodology

"Fastest provider" is not a provider property in isolation. Observed performance depends on origin, workload, request characteristics, network path, connection setup, time, and timer boundaries. Measurement methodology must match the workload being represented.

## Step 007–008 review

Step 007 correctly pushed time filtering into parameterized SQLite queries rather than loading all observations into the dashboard. Windows use explicit inclusive UTC bounds relative to current time; invalid/repeated choices are rejected.

Step 008 review result: **pass; no corrective step required.** `measure_latency()` consumes one provider stream and records TTFT at the first stream item and total latency after full consumption, both from the same monotonic start. The provider is invoked once. TTFT and total latency are saved as separate metric rows in one transaction with a shared timestamp; the dashboard selects metric + time window and keeps all derived values on the same population.

Important Step 008 limitation: total latency depends strongly on output size. It cannot by itself fairly compare requests/providers that produce different amounts of output. Step 009 therefore adds throughput, but must be precise about what is counted: the current simulated provider exposes stream items, not a real provider tokenizer/usage count. Do not call simulated stream items production tokens unless the interface guarantees that meaning.

The current same-timestamp pairing of metrics is sufficient for this small implementation but is not a final request identity model for concurrent production benchmarking.

## Step 009 direction

Step 009 extends the existing single-pass instrumentation to measure output throughput without a second provider request. The metric must have an explicit numerator and denominator, and dashboard units must no longer assume every metric is milliseconds.

This step is intentionally still simulated. Real-provider token accounting, workload/output controls, origin dimensions, and provider comparisons remain later work.