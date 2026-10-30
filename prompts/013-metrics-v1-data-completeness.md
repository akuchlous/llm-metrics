# Step 013 — Metrics v1 data completeness

## Goal

Complete the minimum request-level data model needed before adding more real providers and moving toward production.

This step adds exactly four capabilities:

1. defensible real-provider output token throughput,
2. stable benchmark/workload identity,
3. measurement origin (cloud/region),
4. cache-aware benchmark facts so cached/warm and uncached/cold-ish measurements are never silently mixed.

Do **not** add price scraping, price history, pricing APIs, another provider, scheduling, cloud deployment, PostgreSQL, routing, or Exchange functionality in this step.

## Product context

LLM Metrics is intended to be a useful standalone product for comparing LLM inference price, performance, and reliability. LLM Router and LLM Exchange may later consume its API, but Metrics must remain independently useful.

Pricing remains deliberately simple for now: verified provider/model prices stay in `pricing.py`, and every request stores the effective rates used for its cost calculation. Automated price discovery/history is deferred until Router/Exchange work makes it valuable.

Benchmark cache state matters because prompt/prefix caching can materially change TTFT, latency, and cost. Metrics must preserve enough request-level facts to distinguish cached from uncached measurements rather than silently combining them.

## Requirements

### 1. Add output tokens/sec for successful requests

For real providers, expose a metric named `output_tokens_per_s` with unit `tokens/s`.

It must be based on provider-authoritative output token usage, never chunk count.

Use the existing generation timing boundary from Step 009: generation duration is the interval from the first non-empty output text chunk to the last non-empty output text chunk. TTFT is excluded from generation throughput.

For a successful request with `output_tokens` authoritative provider usage and at least two non-empty output chunks with positive generation duration:

`output_tokens_per_s = output_tokens / generation_duration_seconds`

Document the exact semantics and limitation: provider-reported output token count covers the completed response, while timing is observed at the client stream boundary. This is observed effective generation throughput, not a claim about internal GPU decoding speed.

If the request does not provide a defensible denominator (for example fewer than two non-empty text chunks or non-positive duration), do not fabricate zero/infinity. Omit `output_tokens_per_s` for that request.

Keep `output_chunks_per_s` for backward compatibility and simulated/history continuity for now. Do not rename or reinterpret the existing metric.

Update the metric catalogue, CLI/dashboard/request display as appropriate, queries, tests, and documentation. Public-facing real-provider views should prefer tokens/s over chunks/s when available.

### 2. Add stable benchmark/workload identity

Every new request/attempt must have a non-empty `workload_id` identifying the benchmark case that generated it.

The workload ID describes *what test was run*, not the provider/model or result. Keep it a simple stable string, not a new workload framework/table.

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

### 4. Track cache policy and observed cache usage

Cache state is a benchmark dimension/fact, not a latency metric. Do not use the words `hot`/`cold` as if they are universally provable provider states. Prefer explicit facts about what we requested and what the provider reported.

Add request-level fields sufficient to distinguish:

- the benchmark's intended/requested cache policy, and
- the provider-observed cached input token count when the provider reports it.

Use a small stable cache-policy vocabulary such as:

- `disabled` — benchmark explicitly requested no prompt/prefix cache reuse when the provider API supports such a control,
- `enabled` — benchmark explicitly allowed/requested caching,
- `provider_default` — no explicit cache-control request was made,
- `unknown` — historical/unsupported case where the policy cannot be established.

Choose exact names carefully and document them. Do not claim `disabled` for a provider unless its API gives us a documented mechanism that actually establishes that policy. If a provider cannot guarantee it, use `provider_default`/`unknown` rather than fabricating a cold request.

Add nullable `cached_input_tokens` (or an equivalently precise name) sourced only from provider-authoritative usage metadata. Never infer cached tokens from latency, repeated prompts, chunk timing, or cost. `0` means the provider explicitly reported zero cached input tokens; NULL means unknown/not reported. Preserve this distinction.

For the current OpenAI real benchmark, inspect the existing Responses API integration and official provider behavior already documented/verified by the project before choosing a cache-control request parameter. If the currently used API/model has a documented supported way to disable prompt caching, use it for the controlled benchmark and record `cache_policy = disabled`. If not, do not invent or assume a parameter; record the honest policy instead. Do not make a paid call to verify this step.

If OpenAI's authoritative usage event exposes cached input tokens, parse and carry that value through the provider boundary into the stored request. Keep the generic provider interface minimal: extend `Usage` only with a small optional field if that is the cleanest fit. Do not introduce a generic caching framework.

Expose cache policy and cached-input-token facts in the individual request view. Aggregate performance queries must be structured so future public comparisons can filter/group by cache policy rather than silently mixing incompatible cache populations. Do not build a cache-comparison dashboard yet.

Document user-facing terminology:

- "uncached/cold-ish" means the benchmark requested cache-disabled behavior and/or provider usage reports zero cached input tokens; it is not a claim that every internal provider/model/GPU cache is cold,
- "cached/warm" means provider-authoritative usage indicates cached input reuse or the benchmark intentionally exercised an enabled cache policy,
- unknown/default cache state must remain visible rather than being silently labeled cold.

Do not rotate/randomize prompts merely to manufacture a cold request in this step. Workload comparability is more important. Future dedicated cache experiments can intentionally compare repeated-prefix warm behavior versus uncached behavior.

## Schema / migration

Advance the SQLite schema version using the existing ordered transactional migration mechanism.

Preserve all existing data. Existing request IDs, provider request IDs, outcomes, costs, observations, and timestamps must remain unchanged.

The new request-level facts belong on `requests`; do not turn workload/origin/cache policy/cached token counts into metric rows.

Historical rows may have NULL/unknown cache facts. Do not infer or fabricate cache state for old requests.

Keep request + observation persistence atomic.

## Reliability and semantics

Do not change Step 011 outcome semantics or observed benchmark success-rate denominators.

Do not add retries.

Do not treat request/configuration/account errors as provider reliability failures.

Do not store prompts, generated response text, API keys, arbitrary provider error bodies, or stack traces.

Cache-policy differences define different benchmark populations. Do not silently aggregate cached and explicitly uncached performance into a single claim once the distinction is available.

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
- dedicated warm-vs-cold benchmark loops,
- randomized prompt generation solely to defeat caches,
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
- every newly saved simulated and real-attempt path supplies `workload_id`, `origin_cloud`, `origin_region`, and an honest cache policy,
- provider-authoritative cached input token usage is persisted when supplied,
- cached input `0` remains distinct from NULL/unknown,
- no cached-token value is inferred when the provider does not report it,
- historical migration preserves existing request/observation data and leaves unknown historical facts honestly unknown,
- request views expose workload/origin/cache policy/cached tokens and tokens/s where available,
- performance query code does not require schema redesign to filter by cache policy,
- tests cannot accidentally touch the network,
- `./run.sh` remains working and simulated.

If the OpenAI request is changed to explicitly disable caching, test the serialized request body without making a network call and cite the provider documentation supporting that setting in `DECISIONS.md`.

Run the full test suite and `./run.sh` simulated path. Do not make a paid call.

## Documentation / learning workflow

Update `DECISIONS.md` with durable decisions and `PROJECT_STATUS.md` with current truth.

Create `prompts/013-output.md` summarizing implementation, tests, migrations, choices made, cache semantics, and known limitations.

Follow `prompts/DESIGN_QUESTIONS.md` and create the Step 013 role-specific design-question material under `design-questions/13/`.

Do not modify prior numbered prompts.

## Stop condition

Commit all Step 013 changes and stop.

Do not proceed to adding another provider, automation, cloud deployment, or Step 014. Do not make any additional paid API calls.