# Step 012a — Live validation cleanup and request traceability

## Context

Step 012 introduced the first real provider path using OpenAI `gpt-6-luna` through the Responses API.

The first live request failed and was persisted as `provider_error`:

- llmxchange request id: `6a39b71e28ed4a4daafbd6f056feca97`
- failed after: `5425.6 ms`
- no observations were persisted, as intended

After adding safe diagnostics, a later live request succeeded. The observed successful request was approximately:

- total latency: `3880.7 ms`
- TTFT: `3630.3 ms`
- input tokens: `17`
- output tokens: `14`
- requested max output tokens: `64`
- calculated cost: about `$0.000009`

Do not interpret this single sample as representative model/provider performance. It is only live-path validation.

## Goal

Close Step 012 cleanly now that the real OpenAI path has been exercised. Keep this a small corrective step. Do not start benchmark methodology, scheduling, cloud deployment, PostgreSQL, or another provider.

## Requirements

### 1. Preserve safe local diagnostics

Keep the minimum sanitized diagnostic mechanism needed to understand future provider failures.

It may expose useful structured metadata such as:

- HTTP status
- provider error code/category when safely parsed
- provider request/response identifier
- relevant Responses API event type

It must never print, persist, or include in exception representations:

- API keys
- Authorization headers
- prompts
- generated response text
- arbitrary/raw provider response bodies
- secrets

Stored analytics must continue to use the stable Step-011 outcome categories. Debug diagnostics must not become analytics categories.

### 2. Per-request traceability

We require every benchmark attempt to remain individually traceable using llmxchange's own request UUID.

If OpenAI exposes a stable request or response identifier suitable for diagnostics, capture it safely and associate it with the llmxchange request when practical.

Prefer a minimal schema change if persistence is justified. Do not build distributed tracing, OpenTelemetry, a tracing service, or a generic tracing abstraction.

The desired conceptual relationship is:

```
llmxchange request_id  <->  provider request/response id
```

Provider identifiers are diagnostic metadata, not replacements for our own request identity.

### 3. Pricing provenance

The GPT-6 Luna standard rates used by Step 012 have now been checked against official OpenAI pricing documentation:

- input: `$0.10 / 1M tokens`
- output: `$0.50 / 1M tokens`

Update the pricing provenance/documentation so these rates are no longer marked unverified. Keep the effective rates stored on each request as before.

### 4. Reasoning behavior

Review current official OpenAI documentation for `gpt-6-luna` and the Responses API before changing the request.

If `reasoning.effort = "none"` is officially supported for this model, explicitly use it for this benchmark path. The intent is to make this first latency benchmark a simple, inexpensive text-generation measurement rather than silently using a default reasoning effort.

Document the choice.

If the official documentation available to you does not support this setting, do not guess; leave behavior unchanged and document why.

### 5. Preserve benchmark semantics

Keep:

- exactly one provider call per benchmark attempt
- no automatic retries
- `max_output_tokens = 64` for `real_smoke`
- provider-authoritative usage for input/output tokens
- requested output cap stored separately from actual output tokens
- failed attempts excluded from successful latency/throughput distributions
- `failed_after_ms` separate from successful total latency
- `./run.sh` simulated-only
- tests making zero paid/network calls
- real calls requiring the explicit `real_smoke` command

### 6. Do not add a scheduler or benchmark loop

There must still be no recurring real API calls in this step.

The project-wide operating-budget constraint is `$10/day` including LLM API spend and future hosting/infrastructure. We will design/enforce hosted budget guardrails when deployment/scheduling is introduced. Do not implement a fake whole-project hard cap in this local cleanup step.

### 7. Documentation

Update the durable project documentation to reflect:

- Step 012 live path has now been successfully validated
- pricing is verified if official documentation confirms it
- the failed first request and successful later request are validation history, not benchmark conclusions
- any provider-ID traceability decision
- any reasoning-effort decision
- known limitations that remain

Update at least the relevant sections of:

- `DECISIONS.md`
- `PROJECT_STATUS.md`
- `prompts/chatgpt-conversation.md`

Create `prompts/012a-output.md` describing exactly what changed and the live-validation facts above.

Do not fabricate a provider request ID or any measurement that was not actually observed.

### 8. Tests

Add focused tests for any new behavior, especially:

- sanitized diagnostics do not expose secrets/prompt/response text
- provider identifier parsing/persistence if implemented
- reasoning request field if implemented
- verified pricing provenance
- existing no-network guarantee

Run the complete test suite and `./run.sh` simulated path.

Do not make another paid API call automatically as part of implementation or tests.

## Scope exclusions

Do **not** add:

- second provider/model
- scheduler
- repeated benchmark runs
- cloud deployment
- PostgreSQL
- AWS/GCP infrastructure
- OpenAI SDK or other third-party dependency
- generic SSE framework
- OpenTelemetry/distributed tracing
- materialized cost aggregates
- public benchmark claims based on the single successful request

## Completion

Commit all Step 012a changes and stop.

Report:

1. commit SHA
2. tests/run results
3. exact pricing-provenance change
4. reasoning-effort decision and evidence
5. provider request-ID/traceability decision
6. sanitized debug behavior
7. remaining limitations
8. confirmation that no implementation/test path made an additional paid API call

Do not proceed to Step 013.