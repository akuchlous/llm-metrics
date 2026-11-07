# Project direction log

Concise context not captured by `PROJECT_STATUS.md` or `DECISIONS.md`. Keep only decisions and learning that affect future work; this is not a conversation transcript.

_Last updated: 2026-11-06 (018h)_

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


## Step 018d implementation — PostgreSQL integration proof and migration safety (2026-11-03)

Step 018d is complete. PostgreSQL 17.11 installed locally; disposable database `llm_metrics_018d` used for all integration tests. 13 integration tests pass, 4 `_redact_db_url` unit tests pass; 376 tests total (363 run offline, 13 skipped without `TEST_POSTGRES_URL`); `./run.sh` verified. No GCP resources created; no paid calls.

**Two correctness issues found and fixed:**

`spend_by_model` ORDER BY used `r.c.total_cost.is_(None)` — a bare column reference not in GROUP BY. PostgreSQL's strict GROUP BY mode rejected it with `GroupingError`; SQLite accepted it silently. Fixed by replacing with `func.sum(case((is_success, r.c.total_cost), else_=None)).is_(None)` (the same aggregate expression from the SELECT clause).

`_ensure_schema()` previously called `alembic stamp head` for PostgreSQL with existing tables but no alembic_version row — silently trusting an unknown schema. Now raises `RuntimeError` with an actionable message requiring manual inspection and explicit stamping.

**Credential safety fix:**

`alembic_cfg.set_main_option("sqlalchemy.url", str(engine.url))` replaced by passing a live connection via `config.attributes["connection"]`. This prevents percent-encoded password characters (e.g. `%40`) from triggering Python's `ConfigParser` interpolation and keeps credentials out of Alembic's config logging path. `_redact_db_url()` utility added; `connect()` disposes the engine if `_ensure_schema()` raises.

**What is NOT done:** no Cloud SQL, no Cloud Run, no GCP resources, no paid calls.


## Step 018e security and cloud deployability gate (2026-11-04)

After Step 018d's local PostgreSQL proof, the user requested a security-focused Step 018e that prepares the code to deploy to cloud, with actual Google Cloud deployment as the next step. ChatGPT reviewed the security gaps (unauthenticated local dashboard, cloud runtime readiness, secrets and engine-cache handling, paid-call database preflight, destructive local PostgreSQL test guard, dependencies and explicit execution bounds) and created `prompts/018e-secure-cloud-deployment-readiness.md`. This step adds secure, reproducible Cloud Run web and one-shot job container readiness and targeted safety fixes, but explicitly **does not** create Google Cloud resources or call paid providers. The following separately reviewed step is intended to deploy in existing project `llm-metrics-513617`. The root prompt-authoring contract, four role-specific design questions, testing, output report, marketing checkpoint and stop-for-review requirement remain mandatory; older conversation history is preserved.


## Step 018e implementation — Secure Cloud Run deployment readiness (2026-11-04)

Step 018e is complete. 387 tests total (374 run offline, 13 skipped without `TEST_POSTGRES_URL`); `./run.sh` verified. No GCP resources created; no paid provider calls made.

**What changed:**

`Dockerfile` added: `python:3.13-slim` base, `appuser` non-root identity, hash-pinned dependencies installed via `scripts/install_requirements.py`, `0.0.0.0:${PORT}` via Gunicorn (`--workers 1 --timeout 120`). Two container modes documented in CMD comments: default web service (never makes paid calls) and one-shot job (`python -m llm_metrics.real_benchmark --provider openai --real [--workload ...]` as CMD override). `.dockerignore` excludes `.git`, secrets, `data/`, `.venv/`, tests, and dev-only files.

`gunicorn==23.0.0` and `packaging==24.2` added to `requirements.txt` with sha256 hashes (D057). `web.py HOST` reads `LLM_METRICS_HOST` env var (default `127.0.0.1`); local `./run.sh` behavior unchanged.

Pre-flight DB check: `real_benchmark.run()` calls `storage.connect(db_path)` before announcing the paid call or making any network request. A storage failure (bad credentials, missing database, schema migration conflict) returns exit 2 with the redacted URL and "No request was made". 10 regression tests added in `tests/test_preflight_db_check.py`.

`test_postgres_integration.py` strengthened: `_SAFE_DBNAME_RE` module constant; `setUpClass` refuses database names that lack a recognizable disposable marker (test, dev, bench, tmp, temp, or step suffix like 018d). Module docstring explicitly notes that SSH port-forwarding tunnels make a production database appear at localhost, bypassing the hostname check alone.

`.gitignore` expanded: `.env.*`, key/cert file patterns (`*.pem`, `*.key`, `*.crt`, `*.p12`, `*.pfx`, `service-account*.json`, `*-credentials.json`).

**What is NOT done:** Docker image build (Docker unavailable — marked unverified); pip-audit scan (not available — marked not scanned); no Cloud SQL, Cloud Run, Artifact Registry, IAM, or Secret Manager resources created. Cloud Run deployment checklist written as a non-executed artifact in `prompts/018e-output.md`.

MARKETING CHECKPOINT: not publishable yet. No live cloud data, no periodic benchmark runs.


## Step 018f prompt — gated first OpenAI-only Google Cloud measurement (2026-11-04)

After reviewing 018e's committed implementation, ChatGPT identified a concrete unverified Docker build blocker: `.dockerignore` excludes `scripts/` even though the Dockerfile copies `scripts/install_requirements.py`. The user also decided to publish LLM Metrics using static HTML/charts/versioned JSON behind CDN rather than a public continuously running Flask service; Router/Xchange can consume cached JSON snapshots. Consequently the next cloud milestone is **one Cloud Run Job OpenAI request persisted in PostgreSQL**, not a Cloud Run web service.

ChatGPT authored `prompts/018f-first-openai-cloud-measurement.md`. Its free readiness stage fixes and verifies the container, tests, checks dependencies, performs read-only GCP inspection and verifies current official cost estimates. Creating/enabling GCP services, provisioning databases, uploading secrets and making paid provider calls are **strictly forbidden** until the user explicitly approves a named and bounded plan in Claude's session; invocation of the prompt is not authorization. If approval is absent, Claude must report a truthful blocked checkpoint, commit the output, and stop. With bounded approval, the scope is exactly one OpenAI-only single-task benchmark on Cloud Run Job with no automatic retry, no schedule, no public site. Previously completed prompts and historical log entries remain unchanged.


## Step 018f Stage A implementation — gated first OpenAI Cloud measurement readiness (2026-11-03)

Step 018f Stage A is complete. 392 tests total (379 run offline, 13 skipped without `TEST_POSTGRES_URL`); `./run.sh` verified. No GCP resources created; no paid provider calls made; $0 incurred. Stage B is blocked pending explicit in-session user authorization.

**What changed:**

`.dockerignore` build-context bug fixed: `scripts/` was excluded without a negation, making `scripts/install_requirements.py` absent from the build context. The Dockerfile `RUN python scripts/install_requirements.py` would have silently failed. Fix: added `scripts/` exclusion with a comment and `!scripts/install_requirements.py` negation immediately after. Order is load-bearing: negation must follow exclusion.

Mako upgraded from 1.3.10 to 1.3.12: patches GHSA-v92g-xgxw-vvmm (double-slash path traversal in `TemplateLookup`) and GHSA-2h4p-vjrc-8xpq (backslash URI on Windows). Third CVE (GHSA-5639-2j2p-m4mx, Windows drive-letter, fixed in 1.4.2) is Windows-only and not patched in this Linux container. Advisory scan via OSV API; all other packages clean.

`tests/test_container_config.py` added: 5 offline tests verifying that every Dockerfile `COPY` source is reachable in the build context (not excluded by `.dockerignore`), and that `scripts/install_requirements.py` specifically passes. `@unittest.skipUnless` guard makes the class skip when `Dockerfile`/`.dockerignore` are absent (e.g. in `test_end_to_end_in_a_copy`'s temporary directory copy), fixing a previously failing run.sh copy test.

Architecture decision recorded (D069): public LLM Metrics delivery uses static HTML and versioned JSON snapshots behind CDN, not a continuously running public Flask/Cloud Run service. Flask remains for local/private diagnostics.

**GCP readiness (blocked):** `gcloud` not available; GCP read-only inspection commands provided for user to run. Docker not available; image build unverified. Authorization checkpoint produced in `prompts/018f-output.md` with resource names (project `llm-metrics-513617`, region us-central1), cost estimates (~$10–13/month Cloud SQL, <$0.01 one-time for a single job run), and a one-command teardown plan.

**What is NOT done:** Docker image build (unverified); GCP inspection (gcloud unavailable); Stage B (billable): Cloud SQL, Artifact Registry, Secret Manager, Cloud Run Job — all blocked pending explicit authorization.

MARKETING CHECKPOINT: not publishable yet. No live cloud data; no periodic real benchmark runs; Stage B not authorized.


## Step 018f Stage B implementation — first real OpenAI Cloud Run measurement (2026-11-04)

Step 018f Stage B is complete. One `gpt-6-luna` / `interactive-chat-v1` request executed via Cloud Run Job in gcp/us-central1; stored in Cloud SQL; Cloud SQL immediately deleted post-run. Total spend: under $0.05. No GCP resources created from local machine; all cloud work executed in Google Cloud Shell (D070).

**New architecture decision (D070):** Google Cloud Shell is the preferred environment for all GCP deployment and infrastructure management. Local dev (Python, tests, run.sh) and GitHub (source of truth) are unchanged.

**Measurement result:**
- TTFT: 2013ms | Total latency: 4428ms | Throughput: 128 tokens/s
- Tokens: 1795 input (0 cached) / 300 output (hit cap)
- Cost: $0.00033 | Outcome: success | Environment: prod

**What was provisioned and torn down:** Cloud SQL `llm-metrics-postgres` (db-f1-micro, Enterprise, PG17, us-central1); schema migrated via `storage.connect()`; Cloud Run Job executed once; Cloud SQL deleted. Artifact Registry image `app:sha-9cf8ac9` (~67 MB, free tier), `llm-metrics-job` service account, and budget alert remain.

**Deviations from plan:** Cloud Build used instead of local `docker push` (Cloud Shell Docker daemon cannot reach Artifact Registry — D071); `llm-metrics-build` service account created with minimum permissions; migration via `storage.connect()` rather than `alembic` CLI.

**Data:** measurement row exported to `~/llm-metrics-018f-result/requests.csv` and `observations.csv` in Cloud Shell persistent home (only copy; Cloud SQL deleted). Key fields documented in `prompts/018f-output.md`.

**Ongoing GCP cost:** ~$0.14/month (one secret version + negligible storage). Budget alert: $100/month, notifications at $50/$90/$100.

MARKETING CHECKPOINT: not publishable yet. n=1, single provider, single region. Next step: periodic scheduled runs and/or multi-provider comparison to build a meaningful dataset.


## Step 018g prompt — post-pilot security cleanup and durable baseline (2026-11-04)

Following successful 018f Cloud Run OpenAI pilot and immediate Cloud SQL teardown, the user requested Step 018g and explicitly required all five remaining findings to be addressed: remove unused default compute service account `roles/editor` after dependency inspection; eliminate the stale database URL secret safely; retire a duplicate OpenAI secret version without breaking job references; preserve the one-request/four-observation CSV export in verified private durable storage outside Cloud Shell; and remove only verified orphaned Cloud Build source archives. ChatGPT created `prompts/018g-post-pilot-cleanup-and-backup.md` as a narrowly scoped, approval-gated cloud hygiene and data-preservation step. It explicitly defers scheduling, another paid benchmark, provider onboarding and static public publishing. Claude must present a read-only inspection and precise resource mutation plan, gain explicit scoped user approval, verify each mutation and commit a full report plus four role-specific design Q&A files, and stop for review. Prior history is unchanged.


## Step 018g implementation — post-pilot security cleanup and durable backup (2026-11-04)

Step 018g is complete. Claude ran Phase A read-only inspection in Google Cloud Shell, presented an exact five-action plan with SHA-256 checksums, and the user approved all actions in-session ("aproved for all actions"). Each mutation was independently verified.

1. **HIGH — resolved:** project `roles/editor` removed from the default compute SA. Evidence: the job runs as `llm-metrics-job@`, the only build ran as `llm-metrics-build@`, no Cloud Run services, empty SA-level IAM. Post-check: compute SA has no project roles.
2. **MEDIUM — resolved:** job's `LLM_METRICS_DATABASE_URL` secret reference and Cloud SQL attachment removed; secret deleted (0 Cloud SQL instances). Re-configuration steps recorded.
3. **MEDIUM — resolved:** `OPENAI_API_KEY` v1 disabled, not destroyed; v2 enabled and resolved by the job's `latest` reference. No payloads read.
4. **MEDIUM — resolved (D072):** CSVs backed up to private, versioned `gs://llm-metrics-513617-pilot-backups/snapshots/018f/2026-11-04/` with `SHA256SUMS`; independent download checksums matched; 1 request / 4 observation rows.
5. **LOW — resolved:** three orphaned Cloud Build source tarballs deleted; image `app:sha-9cf8ac9` retained.

**Residual risk found:** with the DB URL removed, the job falls back to container SQLite, so a manual execution would make one ~$0.0003 paid call and lose the result. Proposed fail-closed guard for 018h; do not execute the job meanwhile. `Bash(gcloud *)` Claude setting recommended for narrowing, not changed. No code changes; tests not re-run. Ongoing cost ~$0.13/month.

MARKETING CHECKPOINT: not publishable yet. Stopping for ChatGPT review; Step 018h not started.


## Step 018h prompt — fail-closed cloud-origin guard and durable-store decision (2026-11-06)

Following 018g's residual risk finding (Cloud Run Job falls back to ephemeral container SQLite without a DB URL), the user requested Step 018h as a local code-only change. ChatGPT created `prompts/018h-fail-closed-cloud-storage-and-decision.md` with two objectives: (1) add a fail-closed guard in `real_benchmark.run()` rejecting non-local-origin paid runs without an explicit PostgreSQL DATABASE_URL, and (2) provide an evidence-backed storage architecture analysis for the next OpenAI-only pilot. The prompt explicitly prohibits GCP resource changes, paid calls, or starting 018i.


## Step 018h implementation — fail-closed cloud-origin guard and durable-store decision (2026-11-06)

Step 018h is complete. Code-only change, no GCP resources provisioned or modified.

**Guard added (`real_benchmark.py`):** `_check_cloud_db_url()` helper and guard block in `run()` fire before the API key is read. Any non-local origin (`LLM_METRICS_ORIGIN_CLOUD != "local"`) without an explicit PostgreSQL `LLM_METRICS_DATABASE_URL` returns exit 2 with "No request was made." Rejects: empty/unset, `sqlite://` forms, bare paths (`:memory:`, absolute paths), unsupported schemes. Local-origin SQLite behavior unchanged.

**Tests:** 31 new tests in `tests/test_cloud_db_guard.py`; `test_origin_comes_from_the_environment` updated in `tests/test_openai_provider.py` (now supplies fake PostgreSQL URL + patches `storage.connect` to redirect to test SQLite engine). Full suite: 423 tests, 13 skipped, 0 failures.

**Storage analysis (D073):** Cloud SQL per-session recommended (proven, no code changes, ~$9–11/month idle, delete between sessions). Cloud Storage requires a new backend abstraction (untested). No GCP-native serverless PostgreSQL confirmed usable with existing psycopg2/SQLAlchemy.

**Operational caveat:** Cloud Run Job still runs pre-guard image `app:sha-9cf8ac9`. Do not execute it. 018i closes this by rebuilding and redeploying with the guard active.

MARKETING CHECKPOINT: not publishable yet. Stopping for ChatGPT review; Step 018i not started.


## Step 018i prompt — second controlled OpenAI cloud pilot (2026-11-06)

After Claude completed 018h's cloud-origin fail-closed database guard and comparison of storage options, ChatGPT authored `prompts/018i-second-controlled-openai-cloud-pilot.md`. The step requires separate explicit approvals for first deploying the corrected immutable container and verifying a negative no-database refusal, then provisioning temporary PostgreSQL and executing exactly one OpenAI request. It requires independent private backup verification before teardown, no scheduler or other providers, and a stop-for-review checkpoint. The previously deployed image remains unsafe until replaced; recurring storage design remains a separate decision.


## Step 019 replaces pending 018i (2026-11-06)

The user chose to defer the second OpenAI cloud pilot and instead make the local Docker workflow the next milestone. The unstarted 018i cloud prompt was deleted from main (its history remains in Git). ChatGPT authored `prompts/019-disposable-docker-local-workflow.md`: an opt-in Docker Compose integration path with isolated PostgreSQL, genuine migration/tests, simulated dashboard smoke, project-scoped teardown, and two reproducible clean runs. Native `./run.sh` remains supported because Docker is not installed on the developer machine. Step 019 must audit the latest test-database teardown patch for unsafe database deletion. No GCP changes or paid model requests are included. Review and stop before any cloud pilot.


## Step 019 revised before implementation (2026-11-06)

The user clarified that `./run.sh` itself should run Docker Compose, instead of retaining an independent native Python path. ChatGPT revised the pending `prompts/019-disposable-docker-local-workflow.md`: Docker and Compose are now explicit prerequisites, `./run.sh` runs the complete containerized workflow and dashboard, `./run.sh test` runs disposable tests and smoke, and teardown removes only project-specific containers, networks and disposable database volumes. Verification occurs in Cloud Shell while Docker is absent locally. GitHub history preserves the earlier draft; Cloud Run production is unchanged.


## Step 019 implementation — one-command disposable Docker local workflow (2026-11-06)

Step 019 is complete. Code changes only; no GCP resources provisioned or executed.

**What changed:**
- `compose.yaml` (new): project name `llm_metrics`; `db` service (`postgres:17-alpine`, named volume `db_data`, no host port); `app` service (`Dockerfile.dev`, `LLM_METRICS_COMPOSE_RUN=1`, `TEST_POSTGRES_URL` and `LLM_METRICS_DATABASE_URL` locked to Compose service DNS; `127.0.0.1:8000:8000`)
- `Dockerfile.dev` (new): dev/test image including `tests/` and `docker/entrypoint.sh`; production `Dockerfile` unchanged
- `Dockerfile.dev.dockerignore` (new): BuildKit per-Dockerfile ignore; keeps `tests/` and `docker/` for dev build
- `docker/entrypoint.sh` (new): in-container entrypoint; runs all tests → seeds → measures → serves dashboard (serve mode) or HTTP smoke test (test mode)
- `run.sh` (rewritten): Docker Compose wrapper; requires `docker` + `docker compose`; EXIT trap calls `compose down -v --remove-orphans` (project-scoped); supports `serve`, `test`, `down` modes
- `tests/test_postgres_integration.py`: `setUpClass` skips hostname check in Compose mode; `tearDownClass` is a no-op when `LLM_METRICS_COMPOSE_RUN=1`; added `PostgresGuardTest` (7 offline safety tests); added `from unittest import mock` import
- `tests/test_run_script.py` (rewritten): Docker prerequisite tests; removed native-Python end-to-end test

**Test counts:** 433 total, 13 skipped (PostgreSQL integration — run inside Compose), 0 failures.

**Docker verification: UNVERIFIED.** Docker is unavailable on the development machine. Cloud Shell commands for two clean runs are in `prompts/019-output.md`. Do not mark the step fully accepted until verified.

**a20bf6f tearDownClass:** `tearDownClass` is now a no-op in Compose mode; `compose down -v` handles cleanup. Outside Compose, localhost + dbname guards unchanged (D075). Safety tests added.

MARKETING CHECKPOINT: not publishable yet. Stopping for ChatGPT review; Step 018i (second cloud pilot) not started.


## Step 019.1 implementation — Docker bootstrap script setup.sh (2026-11-06)

Step 019.1 adds `./setup.sh` as a one-time Docker installation helper.

**What changed:**
- `setup.sh` (new): detects OS (Debian/Ubuntu → apt, RHEL/Fedora → dnf, macOS → brew, WSL2 → instructions, other → manual). Checks docker binary, `docker compose version`, daemon access. `--check`: report only, no changes. Interactive mode: shows exact commands, asks Y/N before every sudo operation. Never uses curl-pipe-shell. Never installs PostgreSQL/Python/app services.
- `run.sh`: Docker-missing error now says "Run ./setup.sh" instead of a bare URL
- `tests/test_run_script.py`: added `SetupScriptTest` (5 tests) + `test_no_docker_mentions_setup_sh`

**Test counts:** 440 total, 13 skipped, 0 failures.

**Verification:** `./setup.sh --check` verified locally on Debian (Docker absent): detects apt platform, describes install, exits 1 without changes. Full install path (apt repo + GPG key download) UNVERIFIED (requires sudo + network). Cloud Shell commands in `prompts/019.1-output.md`.

MARKETING CHECKPOINT: not publishable yet. Stopping for ChatGPT review.


## Step 020 authored after Docker verification (2026-11-06)

ChatGPT reviewed the latest GitHub main through commit 71bd99f and the 019.2 report. Step 019/019.2 records two real Docker Compose test cycles, each 444 tests / 5 skips / no failures, PostgreSQL integration executed and dashboard HTTP 200; the independent actual Docker bootstrap installation remains unverified. The 018h cloud-origin fail-closed guard is implemented in source but not yet present in the deployed Cloud Run Job image. The user asked for the next numbered milestone to be Step 020. New pending prompt `prompts/020-guarded-second-openai-cloud-pilot.md` uses separate explicit Approval A for immutable guard deployment and a safe negative test with the provider credential reference removed, and Approval B for exactly one OpenAI paid measurement with temporary PostgreSQL, independent private backup and cost-controlled teardown. No scheduler, new provider, static site implementation or recurring collection in Step 020; future pipeline should emphasize repeatable durable multi-day metrics.


## Step 020 Phase 0 and handoff to Cloud Shell (2026-11-06)

Claude completed Phase 0 locally: real Docker `./run.sh test` (444 tests, 5 skipped, PostgreSQL integration executed, dashboard HTTP 200, clean teardown) and an offline production-image smoke showing the 018h guard refuses gcp-origin runs without PostgreSQL (exit 2, "No request was made") before the key check. Current GCP/OpenAI pricing was rechecked (pilot < $0.10). A read-only inventory script `scripts/gcp/020_inventory.sh` was committed. Because `gcloud` is not installed locally (D070), the user chose to run the cloud phases from a Claude Code session inside Google Cloud Shell; Approvals A and B will be requested there. No cloud changes or paid calls so far. Status recorded in `prompts/020-output.md`.


## Step 020 implementation — guarded second OpenAI cloud pilot complete (2026-11-06)

The user installed `gcloud` locally and asked Claude to run the cloud phases itself instead of from Cloud Shell (D077). After a read-only inventory confirmed the pre-guard job state, the user gave **Approval A** in-session: the `OPENAI_API_KEY` reference was detached first, the image was built by Cloud Build from `0ce36df` (new `cloudbuild.yaml`) and deployed by digest `sha256:1b67b96f…`, and one negative execution exited 2 with the 018h guard message ("No request was made"). The user then gave separate **Approval B**: a temporary Cloud SQL PostgreSQL 17 instance was created and migrated (0 rows), the key and DB secret were attached, and exactly one paid OpenAI `gpt-6-luna` / `interactive-chat-v1` request succeeded (TTFT 2470 ms, latency 5343 ms, 1795/300 tokens, $0.0003295, request `req_d382c497…`). The rows were exported to a new private prefix `snapshots/020/2026-11-06-llm-metrics-benchmark-4mwqz/` with manifest and SHA-256 sums, independently re-downloaded, verified and test-restored; only then were the job credentials detached and the instance and DB secret deleted. Spend < $0.01; ongoing ≈ $0. Rationale: close the production liability of a pre-guard image and prove a complete, auditable single-measurement path before designing recurring collection. Not publishable (n = 2). Stopping for ChatGPT review; Step 021 not started.


## Step 021: inexpensive immutable GCS result records (2026-11-06)

After Step 020 successfully deployed/verified the paid-run guard and backed up a second OpenAI cloud measurement, the user requested Step 021 to make progress toward 15-minute OpenAI-only recurring collection. ChatGPT authored `prompts/021-durable-append-only-gcs-results.md` for an offline-only, GCS-ready atomic single-document result writer/reader (one attempt with observations, immutable create-only key and retry/idempotency semantics). Deliberately do not integrate it with `real_benchmark.run` or weaken the PostgreSQL fail-closed guard in 021: first test data integrity, failure behavior and privacy; separately review/authorize live GCS-backed execution in Step 022 and scheduling thereafter. This reduces the risk of replacing the proven SQL storage path with an untested alternative and avoids per-run Cloud SQL provisioning in the eventual collector. Target 15-minute cadence (96 samples/day/model) once the durable pipeline is proven. No new cloud resources or paid calls under 021.


## Step 021 implementation — immutable per-attempt GCS records, offline (2026-11-06)

Claude implemented `prompts/021-durable-append-only-gcs-results.md`. The point was to remove per-run Cloud SQL from future collection without endangering the 018h guard. Step 021 therefore proves a durable storage contract in isolation before any paid-path integration.

**What was built:** `llm_metrics/object_results.py`:
- a canonical, versioned single-JSON record per attempt (`llm-metrics.attempt.v1`), identical in facts to the SQL row
- a create-only GCS writer: `ifGenerationMatch=0` plus MD5, bounded retries, byte-compare reconciliation of lost acknowledgements and conflicts, no overwrite
- a validated reader and an exact SQL-row mapping
- `google-cloud-storage` 3.17.1 added with its full hash-pinned closure

**Tests and checks:**
- 43 offline tests, using fakes and the real client over a fake HTTP session.
- The Step 020 measurement round-trips exactly.
- Docker `./run.sh test` passed twice: 487 tests, 5 skipped, 0 failures.
- The production image smoke still shows the guard (exit 2).

**Not done:** no paid-path integration, cloud changes or paid calls. The post-response failure window remains; Step 022 mitigations are proposed in the report.

MARKETING: not publishable (n = 2). Stopping for ChatGPT review; Step 022 not started.


## Step 022 implementation — first live GCS-backed OpenAI measurement (2026-11-06)

Claude implemented `prompts/022-first-live-gcs-backed-openai-pilot.md`.

**Phase 0 (offline):**
- an explicit `LLM_METRICS_RESULTS_BACKEND` (`sql` default with the 018h guard unchanged; `gcs` explicit, gcp + OpenAI only)
- `benchmark.measure_attempt` split from SQL persistence
- in GCS mode: configuration refusals before the key or adapter, a real create/read/no-overwrite preflight before the paid request, a pre-allocated attempt id, and exit 3 when the record is not confirmed durable
- a storage-only `gcs_smoke` command
- 24 new tests; the Docker suite passed with 511 tests, 5 skipped

**Phase A (user: "Approve A"):**
- created private bucket `llm-metrics-513617-results` with bucket-only objectCreator + objectViewer for the job service account
- built `sha-ee33635` and deployed it by digest
- ran one storage smoke with no provider key: a synthetic test record, replay accepted, conflict refused, operator SHA-256 match, nothing in `prod`

**Phase B (user: "approved Step B"):**
- attached only the OpenAI key reference and executed once: success, `prod` record `e00ee56c…` (TTFT 1913 ms, latency 5314 ms, 1795/300 tokens, $0.0003295)
- detached the key immediately
- the record was independently downloaded, its SHA-256 and v1 validation passed

**Outcome:** no Cloud SQL, no scheduler, spend under $0.01. The crash window remains open.

Rationale: prove database-free durable collection end to end before scheduling.

MARKETING: not publishable (n = 3). Stopping for ChatGPT review; Step 023 not started.


## Step 023 implementation — bounded 15-minute OpenAI collector activated (2026-11-06)

Claude implemented `prompts/023-15-minute-openai-collector.md`. This combines the earlier 023/024 plan and goes straight to 15-minute cadence.

**Phase 0:**
- `scheduled_collector`: atomic per-slot GCS claims, an exactly-96-slot 24 h policy, a late limit, a GCS server-time clock check, expiry rechecked before the call, no retries, dry-run mode, structured events
- `collector_audit`
- 22 tests (including exactly 96 calls over a full minute-by-minute window, and 8-way concurrency giving 1 call)
- Docker suite: 533 tests, 5 skipped

**Phase A ("Approve A"):**
- dedicated collector job and service accounts; scheduler created paused; invoker scoped to the job; key access removed from the manual job's SA; a preflight-only lifecycle rule; email alerts
- dry runs as the real identity:
  - 17:23: refused as `late_start`, a correct gate action
  - 17:30 slot: claim, duplicate refused, test record
  - expired-policy no-op; an extra one was launched by an interrupted command
  - alert-test ERROR
- The user asked mid-phase about a 1-minute test cadence. After the options were explained (the 15-minute slot gate would turn it into skips and refusals), the user chose to skip it.

**Phase B ("Approve B"):**
- activated 18:00Z → next day 18:00Z (≤ 96 paid requests)
- the first scheduled slot was verified: claim and record agree; TTFT 2087 ms, latency 4941 ms, $0.0003295; audit clean

**Status:** PARTIAL. The 24 h results are not yet observed. The key reference stays attached to the collector job until `stop` is run after the window (the code refuses after expiry).

MARKETING: not publishable. Stopping for ChatGPT review; no further step started.


## Step 023 mid-window progress (2026-11-07)

About 11 hours into the 24-hour pilot, the user asked for the number of collected measurements.

**Audit at 04:56Z:** 44 of 44 begun slots claimed and recorded; 43 successes and 1 recorded `provider_error` (21:30Z, nulls kept, not retried); no missing slots, duplicates or late starts.

**Live counts at 05:14Z:** 45 claims, 45 records, 45 successful executions. Model cost so far is about $0.014.

The Cloud Console's "3 objects" storage figure was the daily-sampled metric reflecting the 018f backups, not a live count.

The user started to ask for the schedule to be made indefinite, then interrupted that request and asked only for a status update and commit. Nothing was changed: the policy still expires 2026-11-07T18:00Z. An indefinite schedule would need a new reviewed step, because the collector deliberately accepts only exactly 24-hour policies.

Status remains PARTIAL until the window closes and is audited.


## gcloud.md project guide added (2026-11-07)

The user asked for a separate, maintained Markdown guide to the project's Google Cloud structure, readable by humans and AI agents. Claude added `gcloud.md` at the repository root, verified against the live project at 2026-11-07T05:14Z, and linked it from `README.md`. It covers:
- the architecture and the order of one scheduled run
- a full inventory: jobs, scheduler, buckets and their layout, secrets, images, monitoring
- identities and least-privilege IAM, including the honest bypass surface
- the data model, the current pilot state, operations commands, the emergency stop
- costs, the change history by step, known gaps, verification commands, a glossary
- an update protocol and safety rules

No cloud changes were made.


## Step 023 progress update (2026-11-07T09:31Z)

The user asked for an updated status report.

**Audit at 09:30:45Z:** 62 of 62 completed slots claimed and recorded. 61 successes and 1 recorded `provider_error` (21:30Z). 0 claims without a record, 0 duplicates, 0 late starts, 0 failed executions. The 09:30Z slot was still starting at audit time.

**So far:** TTFT p50 1649 ms, total latency p50 4293 ms, 115 tokens/s p50. Model cost so far $0.0200.

The window still ends 2026-11-07T18:00Z, and indefinite collection was not enabled. Step 023 remains PARTIAL pending the post-window audit and `stop`.


## Step 024 implemented: offline read-only analytics from immutable GCS records (2026-11-07)

The user asked Claude to implement Step 024 only, offline, without touching the active Step 023 collector, scheduler, credentials or 24-hour pilot, and with no paid calls or cloud changes.

**What was built.** New `llm_metrics.record_analytics` reads a local mirror of the bucket (prod records only), selects one exact population (provider, model, profile, workload, origin, UTC window) and validates every scanned file through `object_results.decode_record`. It writes a canonical, create-only `llm-metrics.analytics.v1` summary containing:
- reliability over all attempts;
- success-only nearest-rank percentiles;
- known cost, with failed attempts counted as cost-unknown;
- per-record SHA-256 evidence;
- machine-readable caveats.

**Why slot completeness comes from claims.** Records alone cannot show missing scheduled slots. Slot completeness therefore comes only from the collector's claims, via `collector_audit`, and it must agree exactly with the selected records; otherwise the run fails.

**Testing.** It was tested on committed synthetic fixtures only. Docker `./run.sh test`: 564 tests, 5 skipped, 0 failures.

**Decision.** D081 records that published numbers will come from this summary, not from the SQL dashboard.

**Not done.** The real pilot mirror was not downloaded or analysed, and no cloud actions were taken. Stopped for ChatGPT review; Step 025 not started.


## Step 025 implemented locally: TTFT Q&A article and metric page (2026-11-07)

The user changed priority slightly: publish useful educational content on llmxchange.com as soon as possible, without waiting for the full OpenAI pilot, but without bypassing review. The site has two purposes: Q&A articles (practical questions, methodology, how the benchmark was built) and metric pages (validated measurements).

**What was built.** Claude implemented Step 025 locally. The new `llm_metrics.static_site` (Jinja2, no Flask, SQL or GCS) builds a home page, the `/llm-performance` hub, the article "How do you measure OpenAI API time to first token (TTFT)?" at `/how-to-measure-openai-ttft`, and `/metrics/openai/ttft`, with the article and metric page linking to each other.
- **Content model:** reviewed editorial text lives in `site_content/` with an explicit `answer_revision`, so new articles need no new templates.
- **Data:** numbers come only from a validated canonical Step 024 summary declared `real` or `synthetic`. Without one, the pages show an explicit no-data state, so the article can be published without any dataset.
- **SEO:** canonical, OG, breadcrumbs matching `BreadcrumbList`, and `Article` JSON-LD without invented dates, authors or images. There is also a meta CSP, build-time checks and an advisory Yoast-inspired report.

**Testing.** All numbers seen were synthetic. Docker `./run.sh test`: 595 tests, 5 skipped, 0 failures.

**Guard change.** One existing guard was narrowed (D082): Jinja2/MarkupSafe are now also allowed in `static_site.py`; Flask remains `web.py`-only.

**Publication path.** The report gives the shortest safe path to publication:
1. review the article and the Step 025 output;
2. decide the publication order;
3. confirm DNS control of llmxchange.com;
4. run one approved, bounded hosting step (Firebase Hosting with clean URLs and no trailing slash is suggested, pricing to be rechecked);
5. set `date_published`;
6. deploy the no-data build and verify it in Search Console.

**Not done.** No hosting, DNS or cloud changes were made. Stopped for ChatGPT review; Steps 026 and 027 not started; Step 023 untouched.


## Step 026 implemented locally: question registry and immutable dated editions (2026-11-07)

ChatGPT reviewed Step 025 and approved proceeding. The user's priority is to make llmxchange.com ready to publish as soon as possible.

**What was built.** Claude implemented Step 026 minimally on the Step 025 `site.json`/`page.json` system:
- **Registry and editions:** per-question `question.json` with an opaque `question_id`. Editions reuse the Step 025 page format, with draft/approved status.
- **Publishing:** `--publish-at` assigns the UTC publication time and freezes edition HTML into a committed archive at `/reports/<date>/<slug>[/rN]`, with manifest `llm-metrics.publication.v1`. Archived bytes are served verbatim and modifications are refused.
- **Pages:** a chronological home feed, a `/questions` directory, and stable question pages with edition history. Editions are canonical to the stable page.
- **Indexing:** the empty metric page is `noindex`; educational pages stay indexable.
- **Redirects:** a `redirects.json` plan for `-latest`.
- **New article:** a draft, "How do we prevent duplicate paid LLM API calls in scheduled benchmarks?". Its facts are tested against the code, and it separates controls from guarantees.

**Testing.** Docker `./run.sh test`: 622 tests, 5 skipped, 0 failures.

**Deliberately deferred.** Dated metric snapshots and sample thresholds were deferred to keep the step minimal, so the prompt's two-dataset metric acceptance check is not met. Data-based answers are refused until snapshots exist.

**Not done.** Nothing has been published (the archive is empty); no hosting, DNS or cloud changes. Stopped for ChatGPT review; Step 027 not started; Step 023 untouched.


## Step 027 implemented offline: Cloudflare-ready site, costs ledger, release lanes (2026-11-07)

ChatGPT accepted Step 026 for the educational Q&A scope. Remaining items were moved forward: `/costs`, pricing Q&A foundations and the ledger format to Step 027; metric snapshots, thresholds and the weekly metrics Q&A workflow to Step 028, mandatory before real results are published. The user's architecture is one public domain (llmxchange.com) on Cloudflare static hosting (free tier preferred), with a polished design and an optional future Flask `/api/*`.

**What was built.** Claude implemented Step 027 offline:
- **Design:** a redesigned site with an "LLM Xchange" brand and top navigation.
- **Costs:** `/costs` from a private reviewed ledger, counting actual charges only. It shows "Full lifetime total not yet verified." until every source is reconciled.
- **Hosting files:** `sitemap.xml`, `robots.txt`, `_redirects`, `_headers` and `404.html`, plus a Workers Static Assets `wrangler.jsonc` using `drop-trailing-slash`.
- **Checks:** a host-routing emulator and a forbidden-content scan.
- **Release lanes:** `publish_runner` with separate editorial and metrics lanes, a cadence config and an emergency switch.

**Testing.** Docker: 647 tests, 6 skipped, 0 failures. Staging builds on a free Cloudflare hostname are protected with noindex, X-Robots-Tag and no sitemap, matching the amended 027 prompt; llmxchange.com is not yet purchased.

**Screenshots.** Not taken: running a third-party headless-browser image was not permitted.

**Not done.** No Cloudflare, DNS or cloud actions. The next step needs Approval A (a `workers.dev` staging deploy). Stopped for ChatGPT review.

## Step 027a: question-first site (2026-11-07)

The user asked to simplify LLM Xchange: the home page becomes a chronological list of questions (50 per page, `/page/N`), every question gets an answer-first page, metrics are presented as questions ("What is OpenAI's TTFT?") that say no validated measurements exist yet, and three educational questions plus the metric question were added as drafts under the existing approval workflow. The design became minimal and typographic. This replaces the Step 027 edition-feed home page (D086) without changing immutable editions. The existing workers.dev staging Worker was updated (approved content only, `noindex, nofollow`); production, DNS, GCP and scheduling were not touched.

## Step 027a follow-up: useful LLM API metrics question (2026-11-07)

The user asked for one more question built from existing work, "Which LLM API metrics are useful, and why?", and for it to be on the static pages. It was added as q0007 `/useful-llm-api-metrics`, approved at the user's request, without numbers or a dated edition, and staging was updated.

## Step 027b implemented: real OpenAI pilot metrics on staging (2026-11-07)

The user wanted to see real OpenAI measurements on the hosted question pages. With the pilot still running (86 of 96 slots due at 15:26Z), a read-only mirror was audited (0 missing) and summarized by the unchanged Step 024 analytics, then published to the existing workers.dev staging Worker through a new staging-only provisional path: "Partial pilot, as of 2026-11-07 15:30:00 UTC", allowlisted public JSON, and a generated evidence view for the still-draft `/openai-ttft` answer. Production gates were not changed; no OpenAI calls or Step 023 changes.

## Local website preview command (2026-11-07)

The user asked for a reusable local preview so the whole site can be checked on their Chromebook before any Cloudflare deploy: `./run.sh site-preview` builds the staging-equivalent site in Docker (approved content, optional locally validated real metrics with the provisional label, nothing frozen) and serves it on http://localhost:8000 with Cloudflare-like routing. The user set a standing rule: local preview and human review come before every staging deployment (D088).

## Step 027c implemented: pilot charts and plan-only restart (2026-11-07)

The owner wanted graphs of the real OpenAI measurements and an easy, safe way to start another 24-hour run. Per-request charts (TTFT, total response time, tokens/s, slot outcomes) were added to the metric page from a sanitized per-slot series that carries the analytics summary's record manifest hash; they are previewed locally with `./run.sh site-preview` and not deployed until the owner says "deploy staging". `./run.sh pilot-plan` prints a bounded 96-slot plan with cost and stop/audit commands and refuses unsafe windows; launching remains a separate Approval C after the original pilot is stopped and audited. No new paid calls, GCS reads or collector changes.

