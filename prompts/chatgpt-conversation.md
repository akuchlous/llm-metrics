# Project direction log

Concise context not captured by `PROJECT_STATUS.md` or `DECISIONS.md`. Keep only decisions and learning that affect future work; this is not a conversation transcript.

_Last updated: 2026-10-30_

## Product direction

`llmxchange` is planned as four independently useful projects:
1. **LLM Metrics** — standalone provider/model price, performance, and reliability measurements.
2. **LLM Quality Bench** — standardized quality tests and scoring.
3. **LLM Router** — route using performance, quality, price, and constraints.
4. **LLM Exchange** — later add bids/asks, capacity, deadlines, and async jobs.

Build useful measurement data first, then quality, routing, and exchange mechanics. LLM Metrics should be independently useful even if Router/Exchange never exist. It should periodically publish provider/model latency, throughput, token usage, effective request cost, errors/reliability, and distributions. Individual benchmark calls may also be published so aggregate claims are auditable.

Pricing is part of Metrics data, but automated price discovery is deferred. For Metrics v1, keep verified provider/model prices in `pricing.py` and store the effective rates used on each request. Do not build price scraping, price-history services, or provider pricing API integrations yet; revisit those when Router/Exchange makes continuously current pricing operationally valuable.

Future real benchmarking needs deliberate dimensions: provider/model, workload category/identity, input size, requested output size, actual output size, and measurement origin (cloud/region/zone), and cache policy/observed cached-input usage. Performance claims are meaningful only for a defined population and methodology. Cached/warm and explicitly uncached/cold-ish measurements must not be silently mixed.

**Publishing/visibility is part of the product direction.** Engineering milestones and later benchmark findings should become useful public material for llmxchange.com and channels such as LinkedIn. Prefer publishing reproducible measurements, methodology, charts, and costs over generic product promotion. The site should eventually make the cost of running the benchmark itself transparent.

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
- Step 013 — Metrics v1 data completeness: authoritative output tokens/sec, stable workload identity, measurement origin, and cache-aware request facts are implemented through schema v6. Review result: pass with known limitations; 192 tests reported passing and no paid call. OpenAI's current official prompt-caching documentation confirms explicit mode with no explicit breakpoints disables prompt caching for GPT-5.6+; live validation of this new request shape is still pending and should be done deliberately later.
- Step 014 — production-web refactor, intentionally split into 014a/014b/... rather than a large rewrite. 014a introduces the Flask application/routing boundary while preserving behavior; 014b will move HTML into Jinja templates; later 014 substeps will separate view/controller preparation from analytics/storage and finish production-web structure before deployment. 014a implemented (Flask app factory, `web.py` → `dashboard.py` → `storage`, hash-pinned `requirements.txt`), pending review.

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

The dependency-free stdlib dashboard was appropriate for the measurement prototype, but `dashboard.py` is now large and mixes HTTP concerns with HTML generation and query/view orchestration. Productionization should separate concerns incrementally, not via a framework rewrite of the measurement core.

Target dependency direction:

`Flask routes/controllers -> application/analytics -> storage`, while benchmark/provider/measurement code remains independent of Flask. HTML moves to Jinja in a separate substep. SQLite remains until the deployment/database step earns PostgreSQL. Do not introduce Django/React/SQLAlchemy merely for architectural appearance.

## Step 012 live validation

The real path is validated, but there are no benchmark conclusions: one successful sample (total latency 3880.7 ms, TTFT 3630.3 ms, 17 input / 14 output tokens, ~$0.000009) is validation only. Early failures led to sanitized diagnostics; a later debug run showed `insufficient_quota` / `credit_balance_exhausted`, teaching that account-billing errors are our problem, not provider unreliability. They are now rejected rather than counted as provider failures.

Traceability: every attempt keeps llm-metrics' own UUID as its identity; OpenAI's `x-request-id` is stored beside it as diagnostic metadata (`provider_request_id`). No tracing system.

`reasoning.effort` is explicitly `none` for the simple text benchmark. Future benchmark methodology must decide reasoning effort deliberately per workload.

Operating budget: the project-wide constraint is **$10/day**, including LLM API spend and future hosting/infrastructure. Budget guardrails are designed and enforced when deployment/scheduling is introduced, not as a fake local cap.

## Step 013 review

Step 013 review result: **pass; no corrective step required before the web refactor.** Parts 1–3 add effective output tokens/sec, required versioned workload identity, and explicit runner cloud/region. Part 4 adds requested cache policy plus provider-authoritative cached input tokens, preserving NULL versus reported zero and separating cache populations without inferring cache state from latency.

Schema v6 preserves historical truth: old workload/origin remain unknown, old cache policy is `unknown`, and cached tokens remain NULL. The request/observation transaction and reliability semantics remain intact. OpenAI uses explicit cache mode with no breakpoints; current official OpenAI documentation confirms that for GPT-5.6+ this does not use prompt caching or create cache writes. The smoke prompt itself is too small to be cache-eligible, and the new cache-control request shape has not yet been exercised by a paid live call.

Known Step 013 limitations are acceptable: output tokens/sec is client-observed and biased high on tiny responses; workload versioning is a convention; origin is configured rather than independently verified; historical requests cannot be backfilled honestly; cached-input pricing is not modeled because controlled OpenAI benchmarks disable caching; aggregate reliability/spend views do not yet filter by cache policy.

## Step 014 direction

Step 014 is a sequence, not one rewrite:
- **014a:** introduce Flask app factory and move HTTP routing/status/query access to Flask while preserving existing rendering and product behavior.
- **014b:** move HTML/CSS generation out of Python into Jinja templates/static assets with no analytics behavior change.
- **014c:** separate route/controller view preparation from analytics/query orchestration so web code does not become the new monolith.
- **014d+:** finish a production-web boundary (API/view organization, production serving/config/test hardening as justified) before cloud deployment. Keep each substep small and reviewable.

Do not combine the Flask refactor with PostgreSQL, provider expansion, scheduling, cloud deployment, authentication, or a frontend SPA.