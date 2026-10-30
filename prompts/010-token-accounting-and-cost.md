# Step 010 — Token accounting and per-request cost

## Goal

Add explicit **input token count**, **actual output token count**, **requested output limit**, and **per-request cost** to the request measurement model so future real-provider benchmarks can explain both performance and economics.

This step is still simulated/test-only. Do not integrate a real provider yet.

Step 009 deliberately measured `output_chunks_per_s`, not tokens/s, because stream chunks are not guaranteed to be tokenizer/API tokens. Step 010 must preserve that semantic honesty.

## Requirements

### 1. Treat request facts separately from metric observations

A single benchmark request now has facts that describe the workload/request as well as measured/derived metrics.

For each request, represent at least:

- provider
- model
- input token count
- requested maximum output tokens
- actual output token count
- TTFT
- total response latency
- existing chunk throughput
- input cost
- output cost
- total cost

Do not force token counts or pricing facts into the existing `metric/value` rows if doing so makes the data model misleading. Make the smallest schema/model change that keeps a coherent **individual request** record and preserves the existing observation history.

The design should support the future public use case: an individual benchmark call can be inspected and its metrics/cost explained together.

### 2. Token accounting semantics must be explicit

The same text can tokenize differently across models/providers. Do not assume a universal tokenizer.

For this simulated step, define a deterministic dummy token-accounting mechanism suitable for tests. Keep it clearly labeled as simulated; do not pretend it matches OpenAI, Anthropic, Google, or another provider tokenizer.

Record separately:

- `input_tokens`: actual token count attributed to the request by the provider/token-accounting boundary
- `requested_max_output_tokens`: the configured output cap/target for the request
- `output_tokens`: actual generated output token count

`requested_max_output_tokens` and `output_tokens` are not interchangeable. A model may stop before the requested maximum.

Do not infer token count from the number of stream chunks. A chunk may contain zero, one, or multiple provider tokens.

### 3. Cost calculation

Introduce explicit simulated pricing for the dummy provider/model:

- input price per 1M tokens
- output price per 1M tokens

Use simple deterministic non-zero prices documented in one authoritative place.

For a successful request derive:

```text
input_cost  = input_tokens  * input_price_per_1M  / 1_000_000
output_cost = output_tokens * output_price_per_1M / 1_000_000
total_cost  = input_cost + output_cost
```

Keep enough precision in storage; round only for display.

Pricing is model/provider metadata, not a property of an individual token. Do not scatter price constants through measurement/dashboard code.

### 4. Historical price correctness

A future provider may change its price. An individual historical request should remain explainable later.

Choose and document a minimal design that preserves the pricing basis used for the request (for example, storing the effective input/output rates with the request in addition to derived cost). Do not build a full pricing-history service in this step.

### 5. Persistence and request identity

Step 009 stores independent metric observations that share a timestamp. Step 008 already identified that timestamp-only pairing is weak.

Because Step 010 introduces request-level facts, give each measured request an explicit stable request/run identity in storage and associate its metric observations with that request if appropriate.

Do not expose provider API request IDs or secrets. This is llm-metrics' own benchmark request identity.

Preserve existing Step 001–009 data through a tested schema upgrade. Historical rows that predate request identity/token accounting may remain unpaired/unknown rather than fabricating values.

### 6. Dashboard / individual call view

Keep the existing aggregate metric/window dashboard working.

Add the smallest useful local view of recent individual measured requests. For each new Step-010 request, show enough information to inspect:

- timestamp
- provider/model
- input tokens
- requested max output tokens
- actual output tokens
- total latency
- TTFT (secondary/diagnostic)
- existing chunk throughput
- input/output/total cost

The primary user-facing latency should be **total latency**. TTFT remains useful diagnostic/streaming information but should not be presented as the only or primary meaning of request speed.

Clearly label dummy/test values as simulated.

No JavaScript or web framework is needed.

### 7. Preserve Step 009 throughput semantics

Do not rename `output_chunks_per_s` to tokens/s merely because token counts now exist. Chunk throughput and token throughput are different measurements.

If exact token timing is not available, do not invent `output_tokens_per_s`. We can add a provider-supported token-throughput metric later when its semantics are defensible.

### 8. Safety and simplicity

Preserve:

- `APP_ENV=test` safe default
- production refusal until a real provider exists
- `127.0.0.1` dashboard bind
- CSP
- parameterized SQL
- no secrets/runtime artifacts committed
- standard-library-only implementation unless a dependency is clearly necessary
- `./run.sh` as the one-command local contract

Do not add abstractions for hypothetical providers beyond what this step requires.

## Acceptance

Tests must demonstrate at least:

1. One dummy request has deterministic input-token accounting.
2. Requested max output tokens and actual output tokens are stored separately.
3. Actual output token count is not derived from stream chunk count; include a test/provider case where chunk count and token count differ.
4. Input, output, and total cost use the documented per-1M-token prices and retain precision.
5. The effective pricing basis for a request is persisted so the historical cost remains explainable after an in-code price change.
6. A new request has an explicit request identity, and its request facts and metric observations can be retrieved together.
7. Existing pre-Step-010 observations survive the schema upgrade without fabricated token/cost/request data.
8. Existing aggregate dashboard metric/window behavior still works.
9. The individual-call view shows the new request facts/cost and labels test data clearly.
10. `./run.sh` remains successful in test mode and `APP_ENV=prod ./run.sh` still refuses safely.
11. All tests pass.

Update `README.md`, `PROJECT_STATUS.md`, `llm_metrics/README.md`, and durable decisions in `DECISIONS.md` as appropriate.

Write `prompts/010-output.md` containing:

- what changed
- tests/run results
- schema/data-model decisions
- exact token-count semantics
- exact pricing/cost semantics
- historical-price decision
- known limitations/review questions
- concise Design Q&A

Follow `prompts/DESIGN_QUESTIONS.md` and create the required `design-questions/10/` role files. Questions must be grounded in the actual Step 010 implementation.

## Out of scope

Do not add:

- a real OpenAI/Anthropic/Google provider
- provider API keys
- a universal tokenizer or tokenizer dependency solely to imitate provider billing
- quality scoring
- routing or bidding
- errors/availability metrics
- cloud/region/origin dimensions
- workload-category taxonomy
- pricing-history service or automatic price scraping
- public deployment/authentication
- exact token-level generation timestamps unless the provider interface genuinely supplies them

## Stop

After Step 010 is implemented, tested, documented, design-question files are written, and committed, stop. Do not start Step 011.