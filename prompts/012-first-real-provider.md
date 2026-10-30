# Step 012 — First real provider, real cost, and benchmark spend

## Goal

Cross the simulated-to-real boundary with **one real LLM provider and one inexpensive text model**, while keeping benchmark spend deliberately tiny and making the cost of running llm-metrics itself visible.

This is the first real-provider step. Keep it narrow. The goal is not broad provider comparison yet; it is to prove that the existing measurement pipeline works honestly against a real streaming API.

Use **OpenAI with `gpt-6-luna`** as the first target unless the current official API documentation shows that model is unavailable to the configured account. The current public list price used when this prompt was written was $0.10 / 1M standard input tokens and $0.50 / 1M standard output tokens. Verify the current official price before implementation and document the source/date. Do not silently substitute a materially more expensive model. If the model is unavailable, stop and report the exact blocker and a cheap alternative; do not choose one automatically.

## Cost principle

**The benchmark system must measure its own economics.**

We want to publish not only model request cost, but also what it costs us to operate the benchmark workload. Future users should be able to answer:

- What does this model cost per benchmark request?
- How much have we spent benchmarking this provider/model over a selected period?
- How much has the benchmark system spent in total over that period?
- How many attempts and successful calls produced that spend?

Keep actual Step-012 API spend tiny. The default real-provider smoke path must make at most **one paid API call per explicit invocation**, with a small fixed prompt and a strict small output cap. Tests must never make paid network calls.

## Requirements

### 1. Add one real provider adapter

Implement one OpenAI text/streaming adapter behind the existing provider boundary.

Preserve the existing measurement semantics:

- one benchmark attempt = one provider API call
- `ttft` = request start to first text output
- `total_latency` = request start through successful full stream consumption
- `output_chunks_per_s` keeps its existing chunk-based meaning
- provider-authoritative usage supplies input/output token counts
- requested maximum output and actual output remain separate
- cost is calculated from the effective pricing basis stored with the request
- provider failures map at the adapter boundary into the Step-011 stable internal categories

Do not redesign the generic provider abstraction unless the real API proves a concrete mismatch. If a small interface change is required, document exactly why.

### 2. Secrets and explicit real-network opt-in

Never commit an API key or print/log it.

Use an environment variable for the provider credential. Document the variable name and setup in README material without including a real value.

Preserve safe local defaults. Running the normal test suite and normal simulated `./run.sh` path must not call a real API or spend money.

Add an explicit real-provider command/path that the developer intentionally invokes. It must fail clearly if the credential is absent.

Do not make paid calls during tests, import time, dashboard startup, schema migration, or simulated runs.

### 3. Tiny controlled benchmark request

Use a deterministic, harmless, text-only benchmark prompt with no tools, search, images, files, or other billable features.

Keep the initial request intentionally small. Default requested output cap should be **no more than 64 output tokens**. Avoid reasoning/tool settings that can create hidden or uncontrolled spend where possible.

The real-provider smoke command should perform exactly one attempt and print a concise summary containing:

- provider
- model
- outcome
- input tokens if known
- requested max output tokens
- actual output tokens if known
- total latency if successful
- TTFT if successful
- output chunk throughput if available
- calculated request cost if known

Do not print the raw prompt or full model response by default.

### 4. Real usage accounting

Use token counts returned by the provider/API when available. Never infer provider token usage from stream chunk count or the dummy tokenizer.

If the provider's streaming API exposes usage only at the end, adapt that honestly to the existing final-Usage contract.

If the real API can complete successfully but does not supply the authoritative usage needed by the current contract, do not fabricate it. Stop and document the API/interface issue rather than weakening the accounting semantics.

### 5. Real pricing and price provenance

Add the selected real model's effective standard input/output prices to the existing pricing mechanism.

Before committing the rates, verify them against the provider's **official pricing documentation**. Document:

- provider
- exact model ID
- input price per 1M tokens
- output price per 1M tokens
- pricing mode/tier used by this benchmark (for example standard synchronous API, not batch/priority unless explicitly selected)
- date the rate was verified
- official pricing source in documentation

Continue storing the effective rates with each request so historical request cost remains explainable if list prices later change.

Do not build automatic price scraping/updating in this step.

### 6. Separate benchmark spend by provider and model

Add a small cost/spend view derived from persisted **real benchmark attempts**.

At minimum, for a selected time window show successful known-cost benchmark spend grouped by:

```text
provider | model | successful paid calls | input tokens | output tokens | total cost
```

Also show a grand total benchmark API spend for the selected window.

The purpose is to make the economics of running llm-metrics transparent and publishable later.

Important semantics:

- do not mix simulated dummy costs into real benchmark spend totals
- failed attempts whose final token/cost usage is unknown must not become `$0.00`; they remain unknown
- show sample/call counts alongside spend
- aggregate by the actual persisted provider/model, not hard-coded display buckets
- preserve raw request-level costs as the source of truth; this step may calculate aggregates at query time because data volume is tiny

Do **not** add hourly/daily materialized cost tables yet. That optimization can be introduced when scale justifies it.

### 7. Make benchmark operating cost publishable

Add a clearly named dashboard section/page such as **Benchmark API Spend** that can later be exposed on llmxchange.com.

It should explain in plain language that this is:

> the API token cost incurred by llm-metrics to run its own benchmark requests

and not:

- the provider's revenue
- universal cost for all users
- infrastructure/cloud hosting cost
- a normalized price comparison independent of workload

For now, this section covers provider API request spend only. Hosting, storage, network egress, domain, and other infrastructure expenses are out of scope for Step 012 and should not be silently included.

### 8. Real vs simulated data must be unmistakable

The current dummy history is simulated. The first real request must not become visually indistinguishable from it.

Keep environments/data populations clearly separated. A user must be able to tell whether a request/aggregate is simulated/test data or a real provider benchmark.

Do not compare a real provider against dummy-provider numbers as if they were peers.

### 9. Failure mapping

Map concrete provider/SDK failures into Step-011 categories at the provider boundary:

- timeout
- rate_limited
- provider_error
- transport_error
- invalid_response where appropriate

Do not persist arbitrary provider exception strings, raw response bodies, prompts, API keys, or stack traces as benchmark data.

Unexpected programming errors remain llm-metrics bugs and must not be mislabeled as provider failures.

### 10. Dependency discipline

A provider SDK dependency is allowed if it materially simplifies correct streaming/error/usage handling. Keep dependencies minimal and pinned/declared appropriately.

Do not introduce a generic multi-provider framework, LangChain, LiteLLM, OpenRouter, queues, schedulers, or cloud infrastructure in this step.

### 11. Tests

Unit tests must use deterministic fakes/mocks and make **zero network calls**.

Test at least:

1. successful real-adapter stream translation into text chunks + authoritative Usage
2. requested output cap is sent correctly
3. missing/invalid usage is not fabricated
4. representative provider failures map to the Step-011 internal categories
5. API key is never persisted or displayed
6. real provider/model pricing lookup and request-cost calculation
7. spend aggregation grouped separately by provider + model
8. grand-total spend calculation
9. simulated dummy request costs are excluded from real benchmark spend
10. unknown failed-request costs do not become zero spend rows
11. normal test/simulated paths make no network calls
12. explicit real path refuses cleanly without credentials
13. schema/data from Steps 001–011 remain readable and preserved
14. all existing tests continue to pass

### 12. Manual smoke run — one paid request only

After all tests pass, perform at most **one** real paid smoke request if a valid API key is available in the developer environment.

Before making it, print enough information to make the action obvious: provider, model, max output tokens, and that exactly one paid request will be made.

Persist the result and report:

- provider/model
- outcome
- input/output token counts
- requested output cap
- TTFT
- total latency
- chunk throughput
- calculated API cost
- effective rates used

Do not loop, retry, or run a batch.

If no credential is available, implementation can still be completed and tested; report the smoke test as not run rather than inventing results.

## Acceptance

Step 012 is complete when:

1. one real provider/model is implemented behind the existing boundary
2. tests never spend money or access the network
3. real execution requires explicit opt-in + credential
4. the default real request is tiny and capped at <=64 output tokens
5. authoritative provider usage supplies token counts
6. official current model pricing is documented with verification date/source
7. per-request cost is persisted with its pricing basis
8. benchmark API spend can be grouped by provider/model and totaled for a selected window
9. simulated costs are excluded from real spend
10. failures preserve Step-011 unknown-vs-zero semantics
11. real and simulated data are clearly distinguishable
12. existing latency/reliability views remain correct
13. one paid smoke request maximum is made during implementation, only if credentials exist
14. `./run.sh` simulated contract remains safe and working
15. all tests pass

Update `README.md`, `PROJECT_STATUS.md`, `llm_metrics/README.md`, and `DECISIONS.md` as appropriate.

Write `prompts/012-output.md` containing:

- what changed
- exact provider/model/API path used
- dependency choice and why
- pricing source, verification date, and effective rates
- test results
- whether a real smoke call was made
- if made: exact measured tokens/latencies/cost (but not prompt/response/secrets)
- failure mapping
- benchmark-spend query/view semantics
- known limitations/review questions
- concise Design Q&A

Follow `prompts/DESIGN_QUESTIONS.md` and create `design-questions/12/` role files grounded in the actual Step-012 implementation.

## Out of scope

Do not add:

- a second real provider or multiple real models
- scheduled/recurring benchmarks
- retries/failover
- cloud deployment or origin/region dimensions
- workload taxonomy
- large input/output matrices
- cache/reasoning-token accounting beyond what is strictly required for honest cost accounting of this chosen model
- quality scoring
- routing/bidding/exchange mechanics
- materialized hourly/daily/monthly cost aggregates
- automatic pricing-page scraping
- infrastructure/hosting-cost accounting
- public internet deployment

## Stop

After Step 012 is implemented, tested, documented, optionally smoke-tested with at most one paid call, design-question files are written, and everything is committed, stop. Do not add a second provider/model or scheduler.