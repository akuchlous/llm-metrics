# Step 009 — Output throughput

Read `PROJECT_STATUS.md`, `DECISIONS.md`, `prompts/README.md`, and `prompts/DESIGN_QUESTIONS.md` first. Preserve existing behavior unless this prompt changes it.

## Goal

Measure **output throughput** for each streamed request so total latency can be interpreted alongside how much output was produced.

## Requirements

- Extend the existing single-pass streamed measurement. Do not make another provider call just to measure throughput.
- Count the output produced by the stream and calculate one clearly defined throughput metric from the same request that produces TTFT and total latency.
- For this simulated-provider step, define exactly what the counted output unit is. Do not claim provider/API token counts unless the current provider interface actually exposes tokens with that meaning.
- Choose and document the throughput metric name and unit. Keep the semantics explicit enough that a future real-provider implementation can replace/adapt the counting source without silently changing what the number means.
- Persist throughput as another observation using the existing observation model if it remains correct. Keep TTFT and total-latency behavior unchanged.
- Extend the dashboard metric selector so throughput can be viewed over the existing 24h / 7d / 30d windows. Labels and units must be correct for the selected metric; do not label throughput as milliseconds.
- Count/latest/p50/p95/p99/chart must all use the same selected metric/window population.
- Preserve explicit rejection of invalid/repeated metric/window query values, loopback-only binding, CSP, and test/prod separation.
- Keep the implementation small; do not introduce a generalized metrics framework or schema redesign for hypothetical future providers.

## Acceptance

- Tests prove TTFT, total latency, and throughput come from one provider invocation and one fully consumed stream.
- Tests prove the throughput calculation against deterministic streamed output and cover the denominator semantics explicitly.
- Tests cover edge cases that would make throughput undefined or misleading and verify the documented behavior.
- Persistence tests prove all metrics from one successful request are saved atomically without mixing metric populations.
- Dashboard tests prove throughput has the correct label/unit and uses the selected time-window population for count, percentiles, and chart.
- Existing TTFT, total-latency, time-window, invalid-input, server/security, and `./run.sh` behavior remains working.
- Full test suite passes.

## Design questions

Follow `prompts/DESIGN_QUESTIONS.md` for Step 009. Create/update `design-questions/09/` with the required engineering-level questions, implementation-grounded answers, and critiques. Update the design-question index if applicable.

## Out of scope

- Real LLM providers or provider-specific tokenizers/usage APIs.
- Input-token throughput.
- Error/availability metrics (next step).
- Cost, quality, routing, workload/origin dimensions, scheduled benchmarking, or aggregate/sketch storage.
- Claiming that simulated stream items are equivalent to production-provider tokens unless that is actually guaranteed by the interface.

## Stop

Update `PROJECT_STATUS.md`, `README.md`, and only durable decisions in `DECISIONS.md`. Write `prompts/009-output.md`, commit Step 009 implementation/tests/docs/design questions, and stop. Do not begin Step 010.