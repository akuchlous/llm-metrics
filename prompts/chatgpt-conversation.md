# Project direction log

Concise context not captured by `PROJECT_STATUS.md` or `DECISIONS.md`. Keep only decisions and learning that affect future work; this is not a conversation transcript.

_Last updated: 2026-11-01_

## Product direction

`llmxchange` is planned as four independently useful projects:
1. **LLM Metrics** — standalone provider/model price, performance, and reliability measurements.
2. **LLM Quality Bench** — standardized quality tests and scoring.
3. **LLM Router** — route using performance, quality, price, and constraints.
4. **LLM Exchange** — later add bids/asks, capacity, deadlines, and async jobs.

Build useful measurement data first, then quality, routing, and exchange mechanics. LLM Metrics should be independently useful even if Router/Exchange never exist. It should periodically publish provider/model latency, throughput, token usage, effective request cost, errors/reliability, and distributions. Individual benchmark calls may also be published so aggregate claims are auditable.

Pricing is part of Metrics data, but automated price discovery is deferred. For Metrics v1, keep verified provider/model prices in `pricing.py` and store the effective rates used on each request. Do not build price scraping, price-history services, or provider pricing API integrations yet; revisit those when Router/Exchange makes continuously current pricing operationally valuable.

Future real benchmarking needs deliberate dimensions: provider/model, workload category/identity, input size, requested output size, actual output size, and measurement origin (cloud/region/zone), and cache policy/observed cached-input usage. Performance claims are meaningful only for a defined population and methodology. Cached/warm and explicitly uncached/cold-ish measurements must not be silently mixed.

**Publishing/visibility and user acquisition are first-class product goals.** Across the overall effort, target approximately **30% Build/Learn and 70% Grow/Distribute**. User research and growth work run in parallel with engineering rather than unnecessarily blocking it. At every meaningful engineering milestone, run a **MARKETING CHECKPOINT**: identify whether there is a publishable finding, a user-research opportunity, or a growth task. `Do not publish yet` is a valid outcome. When a growth opportunity exists, prepare a short handoff containing the completed milestone, evidence/sample size, limitations, relevant links, and suggested opportunity. Prefer reproducible measurements, methodology, charts, user learning, and concrete data stories over generic feature-announcement marketing.

### Benchmark economics

Starting with the first real provider, track and publish the API token cost incurred by llm-metrics to run benchmark requests. Preserve per-request costs and their pricing basis, and expose selected-window spend grouped by provider/model plus a grand total. Keep simulated dummy costs separate from real benchmark spend. Initially aggregate at query time; hourly/daily/monthly materialization can come later when scale justifies it.

Benchmark operating cost must be semantically clear: current spend tracking covers provider API request/token spend only, not hosting, storage, networking, domain, or other infrastructure expenses. Cost should remain attributable by provider/model and eventually by other benchmark dimensions as they are introduced.

Keep real benchmark spend deliberately small during development: tests make no paid calls, normal simulated paths remain offline, real calls require explicit opt-in, and smoke benchmarking uses one inexpensive model with a small fixed prompt and strict <=64 output-token cap.

### Longer-term analytics / exchange metrics

Keep the implementation small now, but preserve an architecture that can grow toward multidimensional provider analytics. Useful dimensions/facts include provider, model, variant/quantization, timestamp/time-of-day, measurement cloud/region/zone, workload/category, input tokens/context length, requested maximum output tokens, actual output tokens, cache policy, cached input tokens, reasoning tokens, finish reason, and later reproducibly defined workload complexity/classifiers.

Useful measurements include TTFT, total latency, generation tokens/sec, end-to-end effective output tokens/sec, request cost, success/error, error/rate-limit type, retry/fallback count, and availability. Public views can emphasize total latency, cost, token counts, throughput, reliability, and whether cached input reuse affected the sample while retaining TTFT as an advanced/diagnostic metric.

For the eventual Exchange, request constraints may include maximum price, latency/deadline, minimum throughput, model/workload requirements, and other buyer constraints. Fulfillment facts may later include bid/ask price, selected provider, actual settlement/fulfillment price, retries/fallbacks, and capacity. Do not implement these speculative fields until a concrete step needs them.

Design principle: **dimensions describe the conditions under which a request was measured; metrics describe what happened.** Keep request identity and request-level facts separate from extensible measurements so later analytics can filter coherent populations without turning every dimension into a metric row.

OpenRouter is a useful product reference: its provider/analytics surfaces emphasize latency/TTFT, throughput, uptime/error behavior, token usage, spend/cost, context length, provider/model/origin dimensions, and routing based on realized price/performance/reliability. llmxchange should retain comparable core facts from the start where practical, then differentiate with controlled benchmark methodology, origin/workload/cache dimensions, and eventual market/fulfillment constraints.

## Development and learning workflow

- GitHub is the source of truth.
- Claude implements one small numbered step; ChatGPT reviews actual code and design material before the next step.
- Material issues get a corrective step before new functionality.
- Used prompts are immutable history once implementation begins; update the current pending prompt when product requirements change before implementation.
- Each step writes `prompts/NNN-output.md` and follows `prompts/DESIGN_QUESTIONS.md` for role-specific learning material.
- Implementation drives learning: after review, discuss one or two questions grounded in the completed step.
- Whenever ChatGPT creates or materially revises a pending numbered prompt, update this file in the same workflow.
- `CODING_GUIDELINES.md` is the standing code-quality contract for all new/modified code. Follow Google Python style where appropriate, with correctness/security/readability ahead of mechanical style. Code and nearby comments/docstrings must be understandable to both human engineers and AI coding agents: descriptive names, explicit responsibilities/invariants, comments that explain non-obvious **why**, no chat-dependent commentary, no stale comments, and no unnecessary narration of obvious syntax. Future numbered prompts should require a coding-guideline review before commit.
- Before implementing commodity functionality, search for a mature, widely adopted library/service. Prefer reuse unless it compromises measurement correctness, security, cost, or an important learning objective.

## Implementation progression

`./run.sh` remains the one-command local developer contract.

- Steps 001–006 — dummy TTFT, local run, SQLite persistence, deterministic history, dashboard, nearest-rank p50/p95/p99: complete and reviewed.
- Step 007 — 24h/7d/30d time windows: complete and reviewed.
- Step 008 — TTFT + total response latency from one streamed request, atomic persistence, dashboard metric selector: complete and reviewed.
- Step 009 — output chunk throughput plus metric units and schema versioning: complete and reviewed.
- Step 010 — token accounting, requested-vs-actual output size, per-request cost, request identity, and individual-call view: complete and reviewed.
- Step 011 — errors, normalized failure categories, persisted failed attempts, and observed benchmark success/failure rate: complete and reviewed.
- Step 012 — first real provider/model (OpenAI `gpt-6-luna`), explicit low-cost real-call path, official-price verification, and publishable benchmark API spend grouped by provider/model: complete; live path validated in Step 012a.
- Step 012a — live validation cleanup: sanitized diagnostics kept, OpenAI `x-request-id` stored per attempt (schema v4), pricing verified against official docs, `reasoning.effort: none` confirmed by the official model page: complete and reviewed; 169 tests reported passing.
- Step 013 — Metrics v1 data completeness: authoritative output tokens/sec, stable workload identity, measurement origin, and cache-aware request facts are implemented through schema v6. Review result: pass with known limitations; 192 tests reported passing and no paid call.
- Step 014 — production-web refactor, intentionally split into small reviewable substeps. 014a Flask boundary: complete/reviewed. 014b Jinja/static presentation extraction: complete/reviewed. 014c analytics-versus-presentation separation: complete/reviewed; 242 tests reported passing. 014d implemented/reviewed: one small versioned read-only JSON aggregate endpoint consumes the same analytics facts as the HTML dashboard; 262 tests reported passing.
- Step 015 — implemented, pending review (283 tests passing, no paid or network call): `llm_metrics/workloads.py` defines the six candidate workloads plus the `smoke.short_text.v2` connectivity check; `benchmark.run_attempt` takes a catalogue workload and refuses non-canonical ones; `python -m llm_metrics --workload <id>`; content pinned by SHA-256 tests. Originally defined as: create a small versioned deterministic workload catalogue (`interactive-chat-v1`, `coding-v1`, `rag-v1`, `summarization-v1`, `extraction-v1`, `agent-tool-v1`) and integrate canonical workload selection into benchmark orchestration. These are candidate benchmark hypotheses subject to user-research refinement, not validated demand. Fairness means reproducible equivalent content/semantics across providers, not forced identical token counts; provider-authoritative token usage remains the observed fact. Material workload changes require a new workload version. No provider expansion or paid comparison calls in this step.
- Step 016 — implemented, pending review (342 tests passing, no paid or network call): one real target per provider with a versioned request profile stored per attempt (schema v7): OpenAI `gpt-6-luna`, Anthropic `claude-haiku-5-5` (thinking disabled), Google `gemini-3.5-flash-lite` (Interactions API, thinking minimal), xAI `grok-4.20-0309-non-reasoning`; standard-library adapters sharing `http_streaming`; cached input priced at the reported cached rate; `python -m llm_metrics.real_benchmark --provider <name> --real` as the one-request pilot path. Originally defined as: four correct real-provider adapters + one explicit benchmark target/profile per provider, preparing the Step 016a paid pilot; no scheduling, experiment orchestration, or paid calls.
- Step 017 — pending: behavior-preserving codebase simplification and reuse. Audit duplicate code, evaluate LiteLLM against the exact Step 016 measurement contract, replace custom provider transport only where fidelity is preserved, assess SQLAlchemy/Alembic for the upcoming Google Cloud persistence phase, remove obsolete/unnecessary code, and report before/after LOC/dependencies. No paid calls or deployment work.

The aggregate dashboard should answer: **How is this provider/model performing, under what workload/origin/cache conditions, and is performance changing?** The individual-call view should answer: **What exactly happened on this benchmark request, how much work did it do, how long did it take, what did it cost, was cached input reused, and did it succeed?** Simulated data must always be clearly labeled.

## Key design learning

Keep raw measurements/facts as the source of truth. Percentiles and costs are derived views/facts whose inputs should remain available. Materialize summaries only when scale/performance justifies it. Percentiles are generally not composable; at scale retain raw data or mergeable distribution summaries rather than only precomputed percentile values.

Define the population before the statistic. The chart and summary statistics must use the same observation population. Eventually a coherent population includes provider/model + origin + workload + request sizes + cache state + time window. More samples do not make a mixed population meaningful.

"Fastest provider" is not a provider property in isolation. Observed performance depends on origin, workload, request characteristics, network path, connection setup, cache reuse, time, and timer boundaries. Measurement methodology must match the workload being represented.

Cache terminology must be evidence-based. "Cold" cannot safely mean every internal provider/model/GPU cache is empty. Record the requested cache policy and provider-authoritative cached-input usage separately. `cached_input_tokens = 0` is an observed zero only when explicitly reported; NULL means unknown/not reported. Prefer terms such as explicitly uncached/cold-ish, cached/warm, provider-default, and unknown, and do not silently aggregate incompatible cache populations.

For user-facing API performance, total completion latency is usually the intuitive primary metric. TTFT remains useful for streaming responsiveness and diagnostics but should not require public users to understand LLM internals. TTFT also does not isolate provider compute from DNS/TCP/TLS/queueing/prefill when those occur inside the measured boundary.

Reliability has a separate population rule: all attempted benchmark calls belong in observed success/failure rate, while successful latency/throughput distributions must not be polluted with fabricated zero values for failures. "Observed benchmark success rate" is more precise than claiming universal provider uptime because measurements represent the runner's own conditions.

Sample size must accompany reliability and percentile claims. Different sample sizes can still be compared statistically, but small populations carry greater uncertainty; raw percentages alone should not be used to claim one provider is more reliable. Confidence intervals/minimum-sample presentation can be added before public rankings require it.

### Web/product architecture direction

Productionization should separate concerns incrementally, not via a framework rewrite of the measurement core.

Current direction after reviewed 014d:

```text
HTML request -> web (Flask/Jinja) -> dashboard -> query -> analytics -> storage
JSON request -> web (Flask)        -> api       -> query -> analytics -> storage
```

`analytics.py` owns population/statistical interpretation and returns natural values. `dashboard.py` owns human-facing formatting, links and chart geometry. `query.py` owns genuinely shared metric/window/population query definitions. `api.py` owns Flask-free machine representation. The separation is test-enforced.

014d established `/api/v1/metrics` as a small v1 compatibility contract. It currently serves one fixed simulated population; provider/model/workload selection belongs after real multi-provider population semantics exist. Do not expand this into a complete REST API, authentication/OpenAPI work, Router, or deployment work prematurely.

## Step 012 live validation

The real path is validated, but there are no benchmark conclusions: one successful sample (total latency 3880.7 ms, TTFT 3630.3 ms, 17 input / 14 output tokens, ~$0.000009) is validation only. Early failures led to sanitized diagnostics; a later debug run showed `insufficient_quota` / `credit_balance_exhausted`, teaching that account-billing errors are our problem, not provider unreliability. They are now rejected rather than counted as provider failures.

Traceability: every attempt keeps llm-metrics' own UUID as its identity; OpenAI's `x-request-id` is stored beside it as diagnostic metadata (`provider_request_id`). No tracing system.

`reasoning.effort` is explicitly `none` for the simple text benchmark. Future benchmark methodology must decide reasoning effort deliberately per workload.

Operating budget: the project-wide constraint is **$10/day**, including LLM API spend and future hosting/infrastructure. Budget guardrails are designed and enforced when deployment/scheduling is introduced, not as a fake local cap.

## Step 013 review

Step 013 review result: **pass; no corrective step required before the web refactor.** Parts 1–3 add effective output tokens/sec, required versioned workload identity, and explicit runner cloud/region. Part 4 adds requested cache policy plus provider-authoritative cached input tokens, preserving NULL versus reported zero and separating cache populations without inferring cache state from latency.

Schema v6 preserves historical truth: old workload/origin remain unknown, old cache policy is `unknown`, and cached tokens remain NULL. OpenAI uses explicit cache mode with no breakpoints; live validation of this new cache-control request shape remains deliberately deferred.

Known Step 013 limitations are acceptable: output tokens/sec is client-observed and biased high on tiny responses; workload versioning is a convention; origin is configured rather than independently verified; historical requests cannot be backfilled honestly; cached-input pricing is not modeled because controlled OpenAI benchmarks disable caching; aggregate reliability/spend views do not yet filter by cache policy.

## Step 014 direction

Step 014 is complete:
- **014a:** complete/reviewed — Flask app factory and HTTP boundary in `web.py`.
- **014b:** complete/reviewed — Jinja templates/static CSS own presentation; dashboard builds no HTML.
- **014c:** complete/reviewed — `analytics.py` owns reusable natural-value analytics; `dashboard.py` owns view formatting; 242 tests reported passing.
- **014d:** complete/reviewed — `GET /api/v1/metrics?metric=&window=` returns one aggregate metric window as JSON facts (numbers, null for unknown, ISO 8601 UTC with `Z`), naming population, metric/unit and window; `samples` (successful observations) and `reliability` (all attempts) remain separate. Shared query definitions live in `query.py`; Flask-free `api.py` serializes analytics results; JSON errors under `/api/` never echo input. HTML remained behaviorally unchanged; 262 tests reported passing.

No further Step 014 refactoring is planned. Return to product work.

## Step 015 direction

Step 015 defines the first real benchmark-workload catalogue before broad provider expansion. Workloads are code-defined, deterministic, versioned methodology. The initial six are hypotheses while five-developer user research runs concurrently. The design must permit later addition/deprecation/versioning without provider/storage/web rewrites.

A workload's approximate input-size target is descriptive, not an exact cross-provider token quota. Send reproducible equivalent content/task semantics, then retain provider-authoritative token usage. Requested output tokens remain a cap; do not retry to force exact output length. Workload definitions should contain no private/proprietary interview or employer material and should not be persisted wholesale merely for traceability; the canonical versioned `workload_id` links a request back to methodology.

Step 015 must finish with `Marketing checkpoint inputs` in its implementation report so the Growth workstream can decide whether methodology/results are publishable. Engineering and user research continue concurrently.

As implemented (pending review): Step 016 adapters receive only `(prompt, max_output_tokens)` from `benchmark.run_attempt(provider, workload, ...)` and report usage through the existing `Usage`; they never define workload content. Provider-specific request settings (for example OpenAI `reasoning.effort`) live in the adapter and are not yet part of the workload id; Step 016/017 should decide how such settings enter the measurement population. Existing aggregate views and `/api/v1/metrics` do not yet filter by workload.

## Step 016 direction

Step 016 adds four real-provider adapters (OpenAI, Anthropic, Google, xAI), one deliberately selected model each, so `interactive-chat-v1` can later be measured across providers through the same pipeline. Provider request settings are measurement conditions: they get their own explicit, versioned request profile stored beside the workload id, not folded into the workload. Reasoning/thinking and cache controls are recorded in each provider's own terms without claiming equivalence. Real execution needs an explicit per-provider command; nothing iterates paid providers automatically.

As implemented: `llm_metrics/targets.py` holds the four profiles plus the simulated one; adapters build request bodies from them and `benchmark.run_attempt` refuses a provider that disagrees with its registered profile. Gemini cannot turn thinking fully off (`thinking_level: minimal`), and only OpenAI's request disables caching; both are documented limits on comparability. The direct adapters and their tests now form a correctness baseline for Step 017's reuse evaluation.

## Step 017 direction

Step 017 is a behavior-preserving cleanup, not a feature milestone. It first audits duplicate code, then evaluates LiteLLM against the exact Step 016 benchmark contract. Reuse provider infrastructure only where TTFT, authoritative usage, cache facts, request IDs, request profiles, failure semantics, privacy, one-request behavior, zero retries/fallbacks/routing, and exact model selection remain intact. It also assesses SQLAlchemy/Alembic for the upcoming Google Cloud persistence phase without forcing a large database rewrite into the cleanup step. Measure before/after LOC and dependencies, remove obsolete or unnecessary code, and keep workloads, pricing provenance, API/dashboard behavior, and all measurement semantics stable. No paid calls or deployment work.