# Project direction log

Concise context not captured by `PROJECT_STATUS.md` or `DECISIONS.md`. Keep only decisions and learning that affect future work; this is not a conversation transcript.

_Last updated: 2026-11-03 (018b)_

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
- Prefer very small implementation increments. When one planned step spans multiple independent concerns, split it into lettered micro-steps (`018a`, `018b`, ...), have Claude complete and commit exactly one micro-step, and have ChatGPT review the actual repo before creating the next prompt.

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
- Step 017 — implemented and reviewed (347 tests passing, no paid or network call): behavior-preserving cleanup. LiteLLM evaluated and not adopted (import-time network fetch, zero-filled unreported usage, different Gemini/xAI endpoints than the request profiles, March 2026 PyPI compromise); duplicated adapter behavior moved into `http_streaming` (`status_failure`, `checked_usage`, `StreamContext`); `real_smoke` delegates to `real_benchmark.run`; shared test fakes; SQLAlchemy Core + Alembic recommended for the Google Cloud persistence step.
- Step 018 sequencing changed before implementation: do **not** live-onboard all four providers first. Prove the whole operational measurement product with the already validated OpenAI path, then add Anthropic/Google/xAI one at a time. The previous oversized Step 018 prompt was removed before implementation because it bundled persistence, runner, cloud runtime, scheduling, analytics, and a multi-day experiment.
- Step 018a — current pending micro-step: OpenAI vertical-slice gap analysis and architecture decision only. Inspect the actual repo, establish what already exists, identify gaps for an unattended multi-day OpenAI experiment, recommend the smallest production architecture/persistence/runtime direction, and choose exactly one next implementation micro-step. No substantive implementation, deployment, scheduling, provider onboarding, or paid calls in 018a. Claude must write `prompts/018a-output.md` and stop for ChatGPT review before 018b is created.

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

## Step 018 direction

The earlier Step 018 plan was deliberately split before implementation because it bundled too many independent concerns. The current strategy is **OpenAI first, complete vertical slice first, then add other providers one at a time**.

Do not require Anthropic, Google, or xAI credentials before productionizing the OpenAI measurement flow. The four adapters remain valid preparation, but the next proof point is an operational product path:

```text
OpenAI exact benchmark path
→ durable production persistence
→ unattended runner
→ cloud runtime/secrets
→ bounded scheduler and cost controls
→ real-data analytics/API/dashboard
→ bounded multi-day OpenAI collection
→ data-quality review
→ then next provider
```

Do not execute that entire sequence as one step. Use small lettered prompts and review each committed increment before creating the next one.

### Step 018a — current

`prompts/018a-openai-vertical-slice-gap-analysis.md` is the current pending prompt. It is intentionally analysis/design only. Claude must inspect the current repository and produce `prompts/018a-output.md` covering:

- which OpenAI vertical-slice pieces already exist;
- what is actually missing for an unattended multi-day OpenAI experiment;
- the smallest sensible production architecture from scheduled execution through durable storage and product surfaces;
- the simplest justified persistence/runtime direction;
- exactly one recommended next implementation micro-step.

018a must not implement persistence, deploy cloud resources, add scheduling, change provider semantics, onboard another provider, or make paid calls. After 018a is committed, ChatGPT reviews the actual repository/output before writing 018b.

## Step 018b — SQLAlchemy Core + Alembic adopted (2026-11-03)

ChatGPT wrote `prompts/018b-sqlalchemy-alembic-persistence.md` after reviewing 018a's gap analysis. The prompt required behavior-preserving portability: replace `sqlite3` with SQLAlchemy Core + Alembic while keeping all null semantics, CHECK constraints, and the v0→v7 legacy upgrade path.

Implemented in this step:
- `storage.py` rewritten: `Table` metadata, `engine.begin()` transactions, parameterized `text()` statements, no ORM.
- `connect(db_path)` now returns a cached `Engine`; callers that were using it as a `sqlite3.Connection` updated.
- Alembic baseline revision `f1a2b3c4d5e6` = v7 schema; fresh databases run `alembic upgrade head`.
- Pre-Alembic local SQLite databases stamped without re-running DDL; legacy migration chain preserved.
- 4 new pinned dependencies: `SQLAlchemy==2.0.36`, `alembic==1.14.1`, `Mako==1.3.10`, `typing_extensions==4.16.0`.
- 344 offline tests pass; `./run.sh` verified end-to-end.

Non-obvious decisions:
- SQLAlchemy `inspect(conn).has_table()` used instead of deprecated `engine.dialect.has_table()`.
- `PRAGMA user_version = 7` is set even for fresh Alembic-managed databases so that `test_fresh_database_is_current_version` (which reads the pragma) continues to pass.
- v3 databases may have no observations table (no observations ever recorded); `_legacy_upgrade()` creates it if absent.

No cloud resources, no PostgreSQL driver, no paid calls. 018c not started.

## Conversation-history policy

`prompts/chatgpt-conversation.md` is an **append-only record of how the user's thinking and the project evolved over time**. It is not a cleaned-up current-state summary.

Rules for future updates:

- Never delete older conversation-history entries merely because the project direction changed.
- Never rewrite older entries to make past thinking look consistent with the current plan.
- Record changes incrementally: preserve the earlier idea/decision, then append the later change and why it changed.
- Contradictions over time are valuable history because they show how the architecture/product thinking evolved.
- Current-state documents such as `PROJECT_STATUS.md` and `DECISIONS.md` may summarize the latest truth; this conversation file should preserve the path taken to get there.
- When ChatGPT creates or materially revises a numbered prompt, append the new context here rather than replacing prior history.

## Step 018c direction — PostgreSQL readiness before cloud provisioning (2026-11-03)

After reviewing `prompts/018b-output.md` and the actual Step 018b `storage.py`, the next task was intentionally narrowed. Step 018b adopted SQLAlchemy Core and Alembic, and its offline SQLite tests passed; however, that did **not** yet demonstrate PostgreSQL compatibility. The connection factory still constructed a SQLite URL from a filesystem path, schema checks used SQLite `PRAGMA`, and seeded-observation deduplication used SQLite-only `insert`. SQLAlchemy table metadata lacked the observation-to-request foreign key present in the Alembic baseline.

This is why the earlier 018a suggestion of combining Cloud SQL provisioning with a first Cloud Run deployment in 018c was superseded: deploy only after the storage boundary is demonstrably ready for a PostgreSQL connection. The new `prompts/018c-postgresql-storage-readiness.md` asks Claude for an explicit PostgreSQL URL/driver, dialect-safe schema lifecycle and inserts, preserved local SQLite behavior, tests with honest compile-only versus integration labels, and no cloud resources or paid provider calls. This is another example of the user's preference for small, reviewed increments. Older plans remain above as history; this paragraph records the change, not a retroactive rewrite.


## Prompt-writing contract and design-question omission detected (2026-11-03)

The user noticed that Step 018's lettered micro-steps were missing the design-question learning material that had accompanied earlier engineering steps. The existing `prompts/DESIGN_QUESTIONS.md` already mandated four role-specific, implementation-grounded design questions per step. The omissions in 018a, 018b, and the in-progress 018c prompts were caused by ChatGPT failing to carry that standing requirement forward, not a change in user preference. The preexisting `design-questions/` index has folders through Step 17 and none yet for 018a/018b.

To prevent requirements being lost as chats and prompts evolve, ChatGPT added `prompts/PROMPT_WRITING_CONTRACT.md`, a reusable authoring and review checklist. Every future numbered prompt should explicitly reference the design-question contract and require role-specific files, a concise Design Q&A in the output, a marketing checkpoint, full offline tests and coding review, an append-only conversation-history entry, and a stop-for-review boundary. Preserve historical 018a–018c prompt files and remedy missed deliverables separately rather than rewriting prompts already used or underway. Claude is still implementing 018c at the time of this entry.


## Root ChatGPT prompt-writing guidelines established (2026-11-03)

To make the standing instructions easier to discover and consistently apply, the user proposed keeping a dedicated `chatgpt-guidelines.md` file, read whenever ChatGPT writes a Claude prompt. ChatGPT created the file at the repository root as an always-read entry point linking `prompts/PROMPT_WRITING_CONTRACT.md`, `prompts/DESIGN_QUESTIONS.md`, `CODING_GUIDELINES.md`, current status/decisions, and this append-only history. It explicitly requires small reviewable steps, four role-specific design-question artifacts for implemented steps, step output, tests, marketing checkpoint, privacy/cost safeguards, and a stop-for-review boundary. The old conversation material above is preserved unchanged.


## Prompt-writing guidance consolidated (2026-11-03)

The user asked to compact `chatgpt-guidelines.md` and `prompts/PROMPT_WRITING_CONTRACT.md` and remove duplicated instructions. The root `chatgpt-guidelines.md` is now a brief mandatory entry point; the contract is the single authoritative detailed checklist. Existing requirements for role-specific design questions, step reports, tests, cost/security safeguards, marketing checkpoints, and append-only history are retained. This change affects prompt-authoring guidance only, not Claude's active implementation prompt. Earlier history remains intact.


## Design questions for Steps 018a and 018b backfilled (2026-11-03)

The user asked to fill the missing design-question learning artifacts while Claude was separately implementing 018c. ChatGPT created four role-specific questions, grounded answers, and critiques for both completed Steps 018a (architecture/gap-analysis decisions) and 018b (SQLAlchemy Core/Alembic migration), under `design-questions/018a/` and `design-questions/018b/`, and added both entries to `design-questions/README.md`. The 018b principal-engineer question explicitly distinguishes tested SQLite behavior from PostgreSQL portability not yet proven. Original 018a/018b prompts and reports were not rewritten. Claude remains responsible for 018c's own design questions when it completes 018c; it may pull these additive commits and merge with its work.


## Step 018c implementation — PostgreSQL-ready storage (2026-11-03)

Step 018c is complete. All 359 tests pass; `./run.sh` verified. PostgreSQL integration not yet verified (no live server).

**What changed:**

`config.get_database_url(environ)` is the new unified URL accessor. It checks `LLM_METRICS_DATABASE_URL` first (sqlite or postgresql scheme only; never echoes the URL in errors), falls back to `sqlite:///{get_db_path()}`. All top-level callers (`__main__`, `real_benchmark`, `seed_history`, `web.create_app()`) now use it.

`storage.connect(db_ref)` accepts both `pathlib.Path` (SQLite, directory created) and URL strings (SQLite string or PostgreSQL). Engine cache keyed by URL string, bounded by number of distinct databases. `_ensure_schema()` branches on `engine.dialect.name`: PostgreSQL skips `PRAGMA user_version` and the legacy v0–v7 bridge entirely; fresh PostgreSQL databases use `alembic upgrade head`. `save_new_observations()` dispatches to `_pg_insert` or `_sqlite_insert` based on dialect.

`_observations.request_id` now carries `ForeignKey("requests.id")` in the Table metadata, matching the Alembic baseline definition.

`psycopg2-binary==2.9.10` added to `requirements.txt` with the Linux x86_64 cp313 sha256 hash. Installed from the pip HTTP cache (no network required after first install).

New tests: `GetDatabaseUrlTest` (7 tests, URL selection, scheme validation, credential redaction), `DialectAndSchemaParityTest` (4 dialect-compilation tests). Two `test_web.py` assertions updated to expect a URL string instead of a `pathlib.Path` in `app.config[DB_PATH_KEY]`.

**What is NOT done:** no Cloud SQL provisioning, no Cloud Run deployment, no GCP resources, no paid calls. Production migration management (running `alembic upgrade head` before traffic) is the operator's responsibility and is documented in `prompts/018c-output.md` and D066.


## Step 018c review and narrower 018d scope (2026-11-03)

Following Step 018c's implementation, Claude reported 359 passing offline tests, `./run.sh` success and all four role-specific `design-questions/018c/` files. GitHub code inspection confirmed dialect selection and PostgreSQL SQL compilation tests but **no real PostgreSQL integration execution**. Two review issues remain important before cloud spending: `storage._ensure_schema` silently stamps unmanaged PostgreSQL tables as the latest Alembic revision without proving they match, and passing credential-bearing SQLAlchemy URLs through migration configuration needs verified secret-safe behavior (including percent characters in passwords).

Accordingly, ChatGPT wrote `prompts/018d-postgresql-integration-and-migration-safety.md`. This narrowly scoped offline step requires a disposable local PostgreSQL integration test of the v7 facts/migrations, fail-closed behavior for unmanaged PostgreSQL schemas, and sanitized Alembic/driver errors; no Cloud SQL or Cloud Run resource creation and no paid provider calls. This supersedes the earlier proposed order of provisioning Cloud SQL immediately after 018c: the reason is to test actual PostgreSQL transaction/constraint behavior and migration safety before incurring infrastructure cost. The existing Google Cloud project `llm-metrics-513617` remains the intended deployment target in a future reviewed step, not authorization to provision. All prior history above is intentionally preserved.
