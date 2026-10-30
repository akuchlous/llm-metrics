# Step 008 — Total response latency

Read `PROJECT_STATUS.md`, `DECISIONS.md`, `prompts/README.md`, and `prompts/DESIGN_QUESTIONS.md` first. Preserve all existing behavior and follow the established engineering rules.

## Goal

Measure **total response latency** in addition to TTFT, persist it as a separate observation, and make it viewable on the existing time-window dashboard.

## Requirements

- Measure total response latency from the same request start used for TTFT until the provider stream is fully consumed.
- Keep TTFT semantics unchanged.
- One provider invocation must produce both TTFT and total-latency results; do not call the provider twice just to measure two metrics.
- Persist TTFT and total latency as separate observations using the existing observations model unless the current design makes that incorrect. If a schema change is truly necessary, explain why before adding it.
- Use one clear metric name for total response latency and document it as a durable decision.
- Extend the dashboard so the user can select **TTFT** or **total latency** while retaining the existing 24h / 7d / 30d windows.
- The selected metric's count, latest value, p50/p95/p99, and chart must all come from exactly the same filtered population.
- Reject invalid or repeated metric query values explicitly; do not silently fall back and do not echo untrusted input.
- Keep the local dashboard bound to `127.0.0.1`; preserve the existing CSP and test/prod separation.
- Keep the implementation small. Do not add a generic metrics framework, provider framework, aggregation service, JavaScript, web framework, or third-party dependency unless the current requirement cannot be met cleanly without one.

## Acceptance

- Tests prove TTFT and total latency are measured from one stream/request and that total latency is never earlier than TTFT for a normal streamed response.
- Tests prove both metrics persist independently and can be queried without mixing their populations.
- Dashboard tests cover both metric selections across a fixed time window, including count/percentiles/chart consistency.
- Existing time-window boundary behavior remains tested.
- Invalid/repeated metric values return HTTP 400; existing invalid/repeated window behavior remains intact.
- Empty data for a selected metric/window renders cleanly.
- `./run.sh` remains the one-command local contract and all tests pass.
- Update `PROJECT_STATUS.md`, `README.md`, and only durable decisions in `DECISIONS.md`.
- Write `prompts/008-output.md` with the implementation summary, tests/run result, design decisions/tradeoffs, limitations, and concise Design Q&A.
- Follow `prompts/DESIGN_QUESTIONS.md` and create the required role-specific Step 08 design-question files. Update the design-question index if present.

## Out of scope

- Real LLM providers.
- Throughput/tokens per second (next step).
- Error/availability metrics.
- Cost/quality/routing.
- Workload, cloud, region, or zone dimensions.
- Precomputed rollups or approximate percentiles.
- Schema redesign for hypothetical future metrics.

## Stop

Commit Step 008 implementation, tests, docs, `prompts/008-output.md`, and the design-question artifacts required by `prompts/DESIGN_QUESTIONS.md`, then stop. Do not begin Step 009.