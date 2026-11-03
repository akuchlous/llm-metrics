# Step 018 — OpenAI end-to-end production metrics vertical slice

## Status

Pending execution. OpenAI live API connectivity has already been validated in earlier work.

## Sequencing decision

We are deliberately changing the order of work.

Do **not** proceed to Anthropic, Google, or xAI live validation yet. The four provider adapters and request profiles from Step 016 remain in the codebase and are not being removed or redesigned. However, before onboarding the remaining providers, finish one complete operational vertical slice using the already live-validated OpenAI target.

The sequence is now:

```text
OpenAI live-validated request path
→ durable production persistence
→ unattended/scheduled benchmark execution
→ real-data analytics/API/dashboard
→ deployment/runtime
→ bounded multi-day OpenAI collection
→ inspect data quality and operational behavior
→ then onboard additional providers one at a time
```

This is a sequencing change, not an architecture change.

The reason is to prove the whole measurement product with one known provider before multiplying provider-specific variables. We want a continuously operating system accumulating trustworthy historical data, not four validated adapters with an unfinished operational path.

Do not assign fixed step numbers to Anthropic/Google/xAI yet. The next step after this vertical slice should be chosen from evidence gathered while operating it.

---

## Objective

Take the known-working OpenAI benchmark path through the complete operational metrics flow with the smallest simple architecture that can later support the same methodology across multiple providers.

Current benchmark target:

- Provider: OpenAI
- Model: `gpt-6-luna`
- Request profile: existing registered OpenAI profile; do not silently change it
- Default workload: `interactive-chat-v1`

The end state of Step 018 is a bounded, unattended OpenAI measurement experiment that can run for multiple days and feed durable storage, analytics, the JSON API, and the dashboard with clearly labelled real measurements.

This is still an engineering/data-quality validation phase. Do **not** publish model-performance conclusions from it.

---

## Product direction — record, do not implement now

Longer term, LLM Metrics / LLM Xchange will expand beyond latency and cost into functional benchmark families such as coding, reasoning, tool use, and agent-security/security-judge performance.

Core product principle:

> **Functional benchmarks can become the intelligence behind routing.**

Public benchmark comparisons should generally use current/latest models when practical so results are relevant and useful. This is later work. Do not expand Step 018 into functional benchmarking, routing, or model comparison.

---

## Required operating mode

Work incrementally. Before implementation, inspect the current repository and identify what already exists versus what is actually missing for the OpenAI vertical slice.

Prefer the smallest next step. Do not build the whole deployment/scheduling system in one change.

For each implementation increment:

1. explain the narrow objective;
2. identify the existing code being reused;
3. state any design decision that materially affects benchmark semantics or operations;
4. implement the smallest justified change;
5. add focused tests;
6. run the full offline test suite;
7. update project status/decision documentation;
8. stop and report before moving to the next substantial increment when user input or an operational decision is useful.

Do not perform unrelated cleanup/refactoring.

---

## Required reading

Before changing code, read at least:

- `CODING_GUIDELINES.md`
- `DECISIONS.md`
- `PROJECT_STATUS.md`
- `prompts/016-output.md`
- `prompts/017-output.md`
- the previous OpenAI live-validation evidence available in the repository
- `llm_metrics/targets.py`
- `llm_metrics/openai_provider.py`
- `llm_metrics/http_streaming.py`
- `llm_metrics/real_benchmark.py`
- `llm_metrics/benchmark.py`
- `llm_metrics/workloads.py`
- `llm_metrics/latency.py`
- `llm_metrics/pricing.py`
- `llm_metrics/storage.py`
- `llm_metrics/analytics.py`
- `llm_metrics/query.py`
- `llm_metrics/api.py`
- `llm_metrics/dashboard.py`
- `llm_metrics/web.py`
- relevant tests

Before writing code, report:

1. which parts of the OpenAI vertical slice already exist;
2. what is still missing for an unattended multi-day OpenAI experiment;
3. the smallest recommended next implementation step;
4. the expected end-to-end architecture from scheduled benchmark → storage → analytics/API/dashboard.

Then wait for approval before the first substantive implementation change.

---

## Benchmark invariants

Automation must not weaken the scientific/measurement contract.

Preserve:

- EXACT execution: exact provider + exact model/profile;
- no routing;
- no fallback;
- no model substitution;
- no hidden continuation;
- no automatic retries unless separately designed, explicitly approved, and represented honestly in measurement semantics;
- canonical versioned workload identity;
- canonical versioned request-profile identity;
- requested output cap separate from actual output;
- provider-authoritative token usage;
- unknown remains unknown/NULL, never fabricated zero;
- cached-input facts only when provider reports them;
- provider request id when available;
- real attempts stored as production/real data;
- simulated and real populations clearly separated;
- prompts, generated responses, API keys, and raw sensitive provider errors are not persisted merely for metrics;
- effective pricing/rates used for each request are preserved with the measurement facts.

If automation requires changing model, endpoint, reasoning, cache controls, workload text, output cap, or another material request setting, stop and explain the methodology impact before changing/versioning it.

---

## Phase A — establish the OpenAI operational baseline

Use the already validated OpenAI live path rather than repeating provider onboarding work unnecessarily.

Confirm from repository evidence that:

- the registered OpenAI request profile is known;
- exactly one request is issued per existing real benchmark command;
- there is no retry/fallback/routing/substitution;
- streaming TTFT behavior was live validated;
- provider usage and request-id behavior were understood;
- pricing was verified at the time recorded;
- successful real measurements persist correctly.

If any of those claims are not supported by repository evidence, identify the gap. Do not invent validation.

Before beginning unattended runs, re-check current official OpenAI model availability and pricing if the recorded verification is stale enough to matter. A material provider change requires an explicit methodology/profile/pricing update, not a silent edit.

---

## Phase B — durable production persistence

The current local SQLite path may be suitable for local development but the multi-day deployed experiment needs durable storage whose lifecycle is independent of a disposable process/container.

Inspect the existing persistence boundary first. Step 017 recommended SQLAlchemy Core + Alembic for the future Google Cloud persistence step; that was a recommendation, not an instruction to adopt complexity automatically.

Choose the simplest durable production persistence appropriate for the selected deployment environment while preserving the existing storage semantics and data model.

Requirements:

- measurements survive process/container restart;
- schema evolution is explicit and testable;
- real and simulated data remain separated;
- historical raw measurement facts remain queryable;
- no benchmark prompt/response content needs to be stored;
- future providers can use the same storage model;
- avoid premature data-warehouse/NoSQL complexity.

Do not migrate merely for fashion. Explain why the chosen persistence mechanism is necessary for the runtime being selected.

---

## Phase C — unattended single-provider benchmark runner

Create the smallest operational mechanism that can execute the existing OpenAI benchmark safely without a person typing the command each time.

The scheduler/runner must preserve EXACT semantics and should be designed so that adding another provider later is configuration/data expansion rather than a new scheduling architecture.

Required properties:

- OpenAI only for Step 018;
- one canonical workload initially unless explicitly expanded later;
- explicit bounded cadence;
- no concurrency initially unless justified;
- no retry by default;
- failures recorded according to established semantics;
- account/configuration errors must not be misrepresented as provider reliability failures;
- secrets come from the deployment environment/secret mechanism, never source control;
- logs must not expose API keys, prompts/responses, or sensitive raw provider errors;
- execution identity/origin should be recorded consistently;
- each attempt remains independently attributable and auditable.

Do not add an `all providers` loop in this step.

---

## Phase D — cost and experiment guardrails

Before enabling unattended paid calls, define an explicit experiment budget and cadence.

The implementation should make accidental runaway spend difficult.

At minimum establish:

- selected workload;
- requests per hour/day;
- expected maximum output cap;
- approximate expected daily cost using current rates;
- experiment duration;
- maximum intended request count;
- a straightforward way to stop the experiment;
- observable failure behavior if credentials/billing/provider access fail.

Prefer simple bounded controls over an elaborate billing subsystem.

Do not enable an indefinite paid loop by default.

---

## Phase E — deployment/runtime

Deploy the smallest runtime that can reliably host:

1. scheduled OpenAI benchmark execution;
2. durable measurement persistence;
3. analytics/API/dashboard access as appropriate.

Google Cloud has been the expected direction in prior planning, but inspect current project decisions before selecting concrete services. Prefer managed/simple components over unnecessary orchestration.

Do not introduce Kubernetes unless there is a demonstrated need.

Deployment must keep the OpenAI key out of source control and use an appropriate secret/environment mechanism.

Document:

- runtime/service chosen;
- scheduler chosen;
- storage chosen;
- secret handling;
- deployment command/process;
- stop/disable procedure;
- approximate infrastructure cost separate from provider API cost.

---

## Phase F — real-data analytics/API/dashboard

The existing product surfaces were originally built around simulated aggregate data plus real request/spend views. Inspect them rather than assuming they already expose the desired production historical metrics.

For the OpenAI vertical slice, ensure we can inspect real measurements over useful windows without confusing them with simulated data.

At minimum, real OpenAI observations should be usable for:

- TTFT;
- total latency;
- output tokens/sec;
- reliability/outcome counts;
- input/output/cached token facts where available;
- per-request cost and aggregate spend;
- workload/profile/origin identity.

Do not over-design visualization. Correct populations, units, timestamps, and provenance matter more than UI polish.

Keep the API/data model extensible enough that future providers become additional populations rather than bespoke endpoints.

---

## Phase G — bounded multi-day OpenAI experiment

Only after persistence, unattended execution, cost bounds, deployment, and real-data visibility are verified should the OpenAI experiment run unattended for multiple days.

Start conservatively. The goal is to validate operations and collect a useful historical series, not maximize sample count.

During the run inspect:

- expected attempt cadence versus actual cadence;
- missing/duplicate executions;
- failure classification;
- TTFT/latency/throughput sanity;
- token/accounting sanity;
- request-profile/workload consistency;
- origin consistency;
- pricing/cost accumulation;
- storage durability across restart/deploy if exercised;
- dashboard/API agreement with stored facts;
- any time-of-day patterns only as observations, not premature causal conclusions.

Do not silently discard outliers or failures. Preserve raw facts and make filtering/aggregation explicit.

---

## Data and future extensibility

Keep measurement facts sufficiently raw and dimensional so later analysis can group by dimensions such as:

- provider/model/request profile;
- workload;
- input size;
- output cap and actual output size;
- origin cloud/region;
- time of day;
- cache facts;
- future workload/functional dimensions.

Do not create speculative columns for every imaginable future metric if the existing extensible model can represent them cleanly. But do not collapse away facts that will be needed for future cross-provider comparisons and routing intelligence.

The future path is:

```text
measure
→ compare
→ publish
→ learn which model is best for which workload/constraint
→ use benchmark intelligence for routing
```

Routing itself is out of scope for Step 018.

---

## Testing and safety

All normal tests must remain offline and must never require provider credentials.

Any live validation must be explicit and user-controlled unless/until it is running inside the deliberately configured bounded production experiment.

Code changes must:

- follow `CODING_GUIDELINES.md`;
- include focused regression tests;
- preserve existing provider adapters/profiles not involved in this step;
- preserve workload hashes unless an explicit new workload version is created;
- preserve privacy and unknown-vs-zero semantics;
- avoid adding provider calls to `./run.sh` or the offline test suite.

---

## Evidence/output

Maintain `prompts/018-output.md` as the implementation and operational record for this vertical slice.

Record, as applicable:

- architecture chosen;
- persistence choice and rationale;
- scheduler/runtime choice and rationale;
- OpenAI model/profile/workload;
- cadence and experiment duration;
- maximum intended request count;
- expected and actual provider spend;
- infrastructure cost estimate/actual where available;
- deployment/origin;
- secret-handling approach (never the secret itself);
- test results;
- live operational validation results;
- failures/issues and fixes;
- data-quality observations;
- commit SHAs for meaningful implementation milestones.

Never record API keys, passwords, MFA codes, payment data, prompts/responses, session tokens, or raw sensitive provider error bodies.

---

## Completion criteria

Step 018 is complete when:

- the OpenAI exact benchmark path runs unattended on an explicit bounded schedule;
- measurements persist durably across the deployed runtime lifecycle;
- real OpenAI data is clearly queryable/viewable through the product's analytics/API/dashboard surfaces;
- TTFT, total latency, throughput, usage, cost, outcome, workload/profile, origin, and request identity semantics remain correct;
- simulated and real data remain clearly separated;
- provider credentials are handled outside source control;
- spend and request count are bounded and understood;
- a multi-day OpenAI run has produced an inspectable historical series, or an external blocker is documented;
- offline tests pass;
- operational setup and stop procedure are documented;
- `prompts/018-output.md` contains the engineering/experiment record;
- no Anthropic/Google/xAI live onboarding was required to complete the vertical slice.

At completion, stop and report:

- what is running;
- where it runs;
- storage/runtime/scheduler architecture;
- sample count and experiment duration;
- total provider API spend and infrastructure cost known so far;
- data-quality findings;
- unresolved operational issues;
- whether the system is ready to add the next provider without redesigning the core measurement pipeline.

Do not automatically start the next provider.

---

## Publication / marketing checkpoint

The OpenAI-only multi-day series can be useful for demonstrating methodology and the product, but it is **not** a cross-provider comparison.

At completion produce a short handoff for the Growth & Marketing workstream containing:

- milestone completed;
- what was measured;
- sample size and duration;
- methodology that can safely be described publicly;
- limitations;
- what is and is not publishable;
- what additional provider data is needed before making comparison claims.

The eventual public comparison should use equivalent methodology and current/latest models across providers.

---

## Focus

> **Finish one complete, trustworthy OpenAI measurement vertical slice before onboarding the next provider.**
