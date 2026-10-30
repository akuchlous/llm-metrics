# Step 013 — Metrics v1 data completeness

## Goal

Complete the minimum request-level data model needed before adding more real providers and moving toward production.

This step adds exactly three capabilities:

1. defensible real-provider output token throughput,
2. stable benchmark/workload identity,
3. measurement origin (cloud/region).

Do **not** add price scraping, price history, pricing APIs, another provider, scheduling, cloud deployment, PostgreSQL, routing, or Exchange functionality in this step.

## Product context

LLM Metrics is intended to be a useful standalone product for comparing LLM inference price, performance, and reliability. LLM Router and LLM Exchange may later consume its API, but Metrics must remain independently useful.

Pricing remains deliberately simple for now: verified provider/model prices stay in `pricing.py`, and every request stores the effective rates used for its cost calculation. Automated price discovery/history is deferred until Router/Exchange work makes it valuable.

## Requirements

### 1. Add output tokens/sec for successful requests

For real providers, expose a metric named `output_tokens_per_s` with unit `tokens/s`.

It must be based on provider-authoritative output token usage, never chunk count.

Use the existing generation timing boundary from Step 009: generation duration is the interval from the first non-empty output text chunk to the last non-empty output text chunk. TTFT is excluded from generation throughput.

For a successful request with `output_tokens` authoritative provider usage and at least two non-empty output chunks with positive generation duration:

`output_tokens_per_s = output_tokens / generation_duration_seconds`

Document the exact semantics and any limitation: provider-reported output token count covers the completed response, while timing is observed at the client stream boundary. This is an observed effective generation throughput metric, not a claim about internal GPU decoding speed.

If the request does not provide a defensible denominator (for example fewer than two non-empty text chunks or non-positive duration), do not fabricate zero/infinity. Omit `output_tokens_per_s` for that request.

Keep `output_chunks_per_s` for backward compatibility and simulated/history continuity for now. Do not rename or reinterpret the existing metric.

Update the metric catalogue, CLI/dashboard/request display as appropriate, queries, tests, and documentation. Public-facing real-provider views should prefer tokens/s over chunks/s when available.

### 2. Add stable benchmark/workload identity

Every new request/attempt must have a non-empty `workload_id` identifying the benchmark case that generated it.

The workload ID describes *what test was run*, not the provider/model or the result. Keep it a simple stable string, not a new workload framework/table.

Examples of the intended concept:
- `smoke.short_text.v1`
- `simulated.default.v1`

Choose sensible IDs for the current simulated path and real smoke path and document them.

Persist `workload_id` on `requests` and expose it in individual request views. Existing historical rows may migrate to NULL/`unknown` only if their original workload cannot be established without fabrication; document the migration choice. New code must always supply a real workload ID.

Do not add prompt text, response text, workload JSON, arbitrary tags, or a workload registry in this step.

### 3. Add measurement origin

Every new request/attempt must record where the benchmark runner executed using two explicit request facts:

- `origin_cloud`
- `origin_region`

These describe the benchmark client/runner location, **not** the provider's serving region.

For local development/smoke execution, use explicit values such as `local` / `unknown` (or another small, clearly documented convention). Do not infer a cloud/region from IP/geolocation and do not call external metadata services.

Make these fields easy to configure through environment variables for future deployment. Pick clear names, validate values conservatively, and document them. Unset local development must remain easy and deterministic.

Persist origin on `requests`, expose it in individual request views, and ensure future aggregate filtering can use these fields without redesigning the request schema. Do not build origin comparison dashboards yet.

Existing rows may be NULL/unknown because their origin was not recorded. Do not fabricate historical cloud/region data.

## Schema / migration

Advance the SQLite schema version using the existing ordered transactional migration mechanism.

Preserve all existing data. Existing request IDs, provider request IDs, outcomes, costs, observations, and timestamps must remain unchanged.

The new request-level facts belong on `requests`; do not turn workload/origin into metric rows.

Keep request + observation persistence atomic.

## Reliability and semantics

Do not change Step 011 outcome semantics or observed benchmark success-rate denominators.

Do not add retries.

Do not treat request/configuration/account errors as provider reliability failures.

Do not store prompts, generated response text, API keys, arbitrary provider error bodies, or stack traces.

## Paid-call boundary

Tests must make zero network calls and zero paid API calls.

Do not make a real provider call while implementing this step.

`python -m llm_metrics.real_smoke` must remain the only explicit paid path and must still perform at most one provider attempt when the user runs it manually.

## Scope exclusions

Do not implement:
- price scraping or price-history service,
- provider pricing APIs,
- second/third provider,
- benchmark scheduler or loops,
- workload matrices,
- cloud deployment,
- PostgreSQL,
- Redis/Kafka/queues,
- public API redesign,
- quality scoring,
- Router or Exchange logic,
- arbitrary analytics/tagging framework.

Let complexity earn its abstraction.

## Verification

Add focused tests covering at least:

- `output_tokens_per_s` uses authoritative `Usage.output_tokens`, not chunk count,
- throughput excludes TTFT and uses the existing first-to-last output timing boundary,
- tokens/s omitted when timing is not defensible,
- existing chunks/s semantics remain unchanged,
- every newly saved simulated and real-attempt path supplies `workload_id`, `origin_cloud`, and `origin_region`,
- migration preserves existing request/observation data and leaves unknown historical facts honestly unknown,
- request views expose workload/origin and tokens/s where available,
- tests cannot accidentally touch the network,
- `./run.sh` remains working and simulated.

Run the full test suite and `./run.sh` simulated path. Do not make a paid call.

## Documentation / learning workflow

Update `DECISIONS.md` with durable decisions and `PROJECT_STATUS.md` with current truth.

Create `prompts/013-output.md` summarizing implementation, tests, migrations, choices made, and known limitations.

Follow `prompts/DESIGN_QUESTIONS.md` and create the Step 013 role-specific design-question material under `design-questions/13/`.

Do not modify prior numbered prompts.

## Stop condition

Commit all Step 013 changes and stop.

Do not proceed to adding another provider, automation, cloud deployment, or Step 014. Do not make any additional paid API calls.