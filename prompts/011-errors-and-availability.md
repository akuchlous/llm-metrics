# Step 011 — Errors, failure classification, and availability

## Goal

Add **benchmark request outcomes** so llm-metrics can measure provider reliability as well as successful-request performance and cost.

A benchmark system that records only successful calls is biased: a provider that is very fast when it succeeds but fails 20% of requests must not appear equivalent to one that succeeds consistently.

This step remains simulated/test-only. Do not integrate a real provider yet.

## Requirements

### 1. Every attempted benchmark request has an outcome

Evolve the Step-010 request model so a benchmark attempt can be persisted whether it succeeds or fails.

At minimum distinguish:

- success
- timeout
- rate limited
- provider/server error
- network/transport error
- invalid provider response/protocol error

Use a small, stable internal classification suitable for future cross-provider comparison. Provider-specific error strings/codes may later be retained separately, but do not make aggregate analytics depend on provider-specific wording.

Do not store stack traces, secrets, API keys, prompts, or arbitrary raw exception text in the database.

### 2. Preserve semantic honesty for partial/failed requests

A failed request may not have trustworthy final token usage, cost, TTFT, total completion latency, or throughput.

Do not fabricate zeros for facts that are unknown. Unknown is different from zero.

Preserve the existing meanings:

- `total_latency` means a successfully completed response from request start through fully consumed stream.
- `ttft` means time to first text output when one was actually observed.
- `output_chunks_per_s` keeps its Step-009 definition.
- token counts/cost come from authoritative `Usage` at the provider boundary, not chunk counts.

If schema changes are needed so failed attempts can have unknown token/cost fields, make the smallest clear migration and document the nullability semantics.

It is useful to know how long a failed attempt consumed before failing, but do not overload `total_latency` with a different meaning. If you record failure elapsed time, give it an explicit name and definition.

### 3. Deterministic simulated failure modes

Extend the dummy/test provider boundary with deterministic ways for tests to exercise representative failures without network calls or randomness.

Keep the normal `./run.sh` path successful and deterministic.

Tests should be able to trigger at least timeout, rate-limit, provider/server error, transport error, and malformed/missing usage behavior without sleeping for long real time.

Do not build a general fault-injection framework.

### 4. Availability / success-rate analytics

Add a simple reliability view derived from persisted attempts.

For a selected provider/model and time window, define:

```text
attempts      = all persisted benchmark attempts in the population
successes     = attempts whose outcome is success
failures      = attempts whose outcome is not success
success_rate  = successes / attempts
failure_rate  = failures / attempts
```

Show sample count. If there are no attempts, show no rate rather than 0% or 100%.

Also show failure counts by internal failure category so a user can distinguish rate limiting from provider errors, timeouts, transport failures, and invalid responses.

Call this **observed benchmark success rate** (or similarly precise wording), not universal provider uptime. Our runner observes only its own requests from its own measurement conditions.

### 5. Keep successful performance populations clean

Existing latency/throughput percentile charts should continue to describe successful measurements only. Failed attempts must contribute to reliability analytics but must not silently inject zero latency/throughput values into p50/p95/p99.

This separation is important:

```text
all attempts  -> success/failure rate
successful attempts with metric -> latency/throughput distributions
```

### 6. Prepare for future real-provider errors without integrating one

Design the internal failure categories so a future OpenAI/Anthropic/Google adapter can map its native errors into the common categories.

Do not create provider-specific adapters now. Do not guess provider-specific HTTP/error semantics beyond what is needed for the internal abstraction.

Keep retry behavior out of this step. One benchmark attempt is one provider call. A future step can decide whether retries are separate attempts, part of a logical request, or both.

### 7. Individual request view

Extend `/requests` minimally so each attempt clearly shows success/failure and, for failures, the normalized failure category.

Successful rows should retain the Step-010 token/cost/performance information. Unknown facts for failures should display as unavailable, not zero.

Keep test/simulated labeling clear.

### 8. Storage and migration

Preserve all Step-001–010 data through a tested schema upgrade.

Existing Step-010 request rows were successful requests, so it is valid for the migration to classify those existing request rows as success if that is explicitly documented and tested. Older standalone observations with no request identity remain unpaired and must not be fabricated into attempts.

Keep request outcome + available request facts + linked observations transactionally coherent.

### 9. Safety and simplicity

Preserve:

- `APP_ENV=test` safe default
- production refusal until a real provider exists
- `127.0.0.1` dashboard bind
- CSP
- parameterized SQL
- no secrets/runtime artifacts committed
- standard-library-only implementation unless clearly justified
- `./run.sh` as the one-command local contract

Do not add retries, schedulers, queues, alerting, or distributed infrastructure.

## Acceptance

Tests must demonstrate at least:

1. A successful dummy request is persisted with outcome `success` and keeps all Step-010 token/cost/metric behavior.
2. Deterministic simulated timeout, rate-limit, provider/server, transport, and invalid-response failures map to stable internal failure categories.
3. Failed attempts are persisted rather than disappearing from the dataset.
4. Unknown token/cost/performance facts on failures are not fabricated as zero.
5. Failed attempts do not contaminate successful latency/throughput percentile populations.
6. Success/failure rate is calculated from all persisted attempts in the selected population and includes sample count.
7. Failure counts by category are correct.
8. A population with no attempts reports no availability percentage rather than a misleading value.
9. `/requests` clearly distinguishes successful and failed attempts and displays unavailable fields honestly.
10. Step-010 schema/data upgrades without loss; existing Step-010 request rows are treated consistently as historical successes, while pre-Step-010 unpaired observations remain unchanged.
11. A failed attempt and any facts/observations retained for it are saved atomically.
12. Existing aggregate metric/window dashboard behavior still works.
13. `./run.sh` succeeds in test mode and `APP_ENV=prod ./run.sh` still refuses safely.
14. All tests pass.

Update `README.md`, `PROJECT_STATUS.md`, `llm_metrics/README.md`, and durable decisions in `DECISIONS.md` as appropriate.

Write `prompts/011-output.md` containing:

- what changed
- tests/run results
- exact success/failure semantics
- internal failure categories and mapping boundary
- schema/migration decisions, especially unknown/null fields
- availability calculation and population definition
- what happens to partial measurements on failure
- known limitations/review questions
- concise Design Q&A

Follow `prompts/DESIGN_QUESTIONS.md` and create the required `design-questions/11/` role files. Questions must be grounded in the actual Step 011 implementation.

## Out of scope

Do not add:

- a real OpenAI/Anthropic/Google provider or API keys
- retries or retry policies
- automatic provider failover
- SLOs/alerts
- scheduler/cron/cloud deployment
- cloud/region/origin dimensions
- workload-category taxonomy or prompt-complexity scoring
- cache-hit metrics
- routing or bidding/exchange mechanics
- quality scoring
- provider-specific dashboards
- raw prompt/response persistence
- generic observability infrastructure

## Stop

After Step 011 is implemented, tested, documented, design-question files are written, and committed, stop. Do not start the first real-provider integration.