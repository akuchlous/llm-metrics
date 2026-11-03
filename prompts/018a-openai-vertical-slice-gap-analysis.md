# Step 018a — OpenAI vertical-slice gap analysis and architecture decision

## Status

Pending execution.

## Objective

Do **not** implement the full OpenAI production vertical slice in this step.

This micro-step exists only to inspect the current repository, establish what already works, identify the remaining gaps for a bounded multi-day OpenAI measurement experiment, and recommend the smallest next implementation step.

The broader sequencing decision is:

```text
OpenAI already-live-validated request path
→ durable production persistence
→ unattended single-provider execution
→ cloud runtime + secret handling
→ bounded scheduling/cost guardrails
→ real-data analytics/API/dashboard
→ bounded multi-day OpenAI experiment
→ review + marketing checkpoint
→ add other providers one at a time
```

Step 018a covers only the first architecture/gap-analysis decision before those implementation steps.

Do not onboard Anthropic, Google, xAI, or DeepSeek in this step.
Do not add scheduling, deployment, persistence migrations, dashboards, or production services in this step.

---

## Why this step is intentionally small

The previous Step 018 prompt combined persistence, automation, deployment, analytics, scheduling, and a multi-day experiment. That is too large for the project workflow.

From this point forward, productionization should proceed as a sequence of small reviewable commits. Each sub-step should have one narrow responsibility, focused tests, an output record, and a review before the next substantial change.

---

## Required reading

Before making any recommendation, read at least:

- `CODING_GUIDELINES.md`
- `DECISIONS.md`
- `PROJECT_STATUS.md`
- `prompts/016-output.md`
- `prompts/017-output.md`
- the repository evidence for the earlier successful OpenAI live validation
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

Also inspect the current repository tree and recent implementation history where useful.

---

## Existing architectural constraints to preserve

Treat these as requirements, not optional suggestions:

- OpenAI is the only provider being operationalized first.
- The existing registered OpenAI provider/model/request profile remains the benchmark target unless verified external changes require an explicit methodology update.
- EXACT execution semantics: exact provider + model/profile.
- No routing.
- No fallback.
- No model substitution.
- No hidden continuation.
- No automatic retries by default.
- Canonical versioned workload identity.
- Canonical versioned request-profile identity.
- Requested output cap remains separate from actual output.
- Provider-authoritative token usage.
- Unknown remains NULL/unknown; never fabricate zero.
- Cached-input facts only when provider reports them.
- Provider request ID retained when available.
- Real and simulated populations stay clearly separated.
- Do not persist prompts/responses/API keys/raw sensitive provider errors merely for metrics.
- Preserve effective pricing/rates used for each request.
- Local machine is for development and explicit manual smoke validation only.
- Persistent multi-day execution belongs on Google Cloud.
- Production total budget target remains <= $10/day across provider API + infrastructure.
- Prefer simple managed services; no Kubernetes unless demonstrated necessary.
- Before implementing commodity functionality, evaluate mature reusable libraries/services first, but do not sacrifice measurement fidelity.

---

## Work required in Step 018a

### 1. Establish the current OpenAI baseline from repository evidence

Report what is already implemented and supported by evidence, including:

- exact OpenAI provider/model/request profile;
- workload selection path;
- one-request real benchmark command;
- streaming/TTFT semantics;
- token usage extraction;
- provider request ID handling;
- pricing/cost calculation;
- persistence behavior;
- real-vs-simulated environment/population handling;
- current HTML/API/dashboard support for real measurements;
- no-retry/no-fallback behavior;
- prior live-validation evidence.

Do not claim anything that cannot be supported by repository evidence.

### 2. Identify the minimum gaps for an unattended multi-day OpenAI experiment

Produce a concise gap list grouped by responsibility, for example:

- persistence durability;
- schema/migration portability;
- unattended runner;
- cloud execution/runtime;
- secret handling;
- scheduling;
- cost/request-count guardrails;
- production-origin recording;
- real-data analytics/API/dashboard population selection;
- operational logging/stop procedure.

For each gap, distinguish:

- genuinely missing;
- already partly implemented;
- not needed yet.

Avoid inventing speculative future requirements.

### 3. Recommend the smallest next implementation step

Choose exactly **one** next micro-step after 018a.

The likely candidate is durable production persistence, but do not assume that without inspecting the code and intended runtime.

The recommendation must state:

- narrow objective;
- files likely affected;
- what should explicitly remain out of scope;
- why this is the smallest dependency-unblocking step;
- expected tests;
- whether it requires any paid/provider call (prefer no).

Do not implement that next step in 018a.

### 4. Recommend the simple end-to-end target architecture

Provide a small architecture diagram from scheduled benchmark to public/read surfaces, using only components justified for the near-term OpenAI experiment.

Compare the practical Google Cloud choices only as needed to select a direction. Prior planning expected something similar to:

```text
Cloud Scheduler
    ↓
Cloud Run Job
    ↓
OpenAI exact benchmark
    ↓
managed durable database
    ↓
analytics/query layer
    ↓
Cloud Run Flask web/API
```

But validate whether that remains the simplest sensible architecture before recommending it.

For persistence, explicitly revisit the Step 017 recommendation of SQLAlchemy Core + Alembic. Explain whether that abstraction/migration approach is justified now. Also identify the simplest suitable managed Google Cloud database/storage option for this low-volume measurement workload; do not automatically choose an expensive service if a cheaper suitable managed option exists.

Do not provision any cloud resources in this step.

### 5. Define the micro-step sequence

Recommend the remaining Step 018 sub-step sequence using small increments, e.g. 018b, 018c, etc.

Each proposed sub-step should have one dominant responsibility and a clear review boundary.

Do not assign implementation details beyond what is needed to make the sequence understandable.

---

## No substantive implementation in 018a

This is primarily an analysis/design step.

Allowed changes are limited to documentation needed to record the decision, such as:

- `prompts/018a-output.md`
- `PROJECT_STATUS.md`
- `DECISIONS.md` if and only if a real architectural decision is made
- `prompts/chatgpt-conversation.md` / project direction log as appropriate

Do **not** modify production Python behavior, database schemas, deployment files, dependencies, or cloud resources in this step unless the user explicitly authorizes a tiny corrective documentation-only exception.

Do not make paid provider calls.
Do not make OpenAI API calls just to reconfirm already-recorded evidence.

---

## Output required

Create `prompts/018a-output.md` containing:

1. current OpenAI vertical-slice capabilities already present;
2. evidence/gaps table;
3. minimum missing pieces for a bounded multi-day run;
4. recommended near-term Google Cloud architecture;
5. persistence recommendation, including whether SQLAlchemy Core + Alembic should now be adopted;
6. exactly one recommended next micro-step;
7. proposed 018b/018c/... sequence;
8. risks/unknowns that need user input later;
9. confirmation that no paid provider calls and no substantive runtime changes were made.

Keep the output concise enough to review easily.

---

## Completion criteria

Step 018a is complete when:

- the repository has been inspected rather than assumptions being made;
- current OpenAI capabilities are separated from missing operational pieces;
- the smallest next implementation step is clearly identified;
- a simple Google Cloud target architecture is recommended;
- persistence/runtime choices are reasoned about explicitly;
- the remaining Step 018 work is decomposed into small reviewable sub-steps;
- no paid calls were made;
- no substantive production implementation was performed;
- `prompts/018a-output.md` exists;
- Claude stops for review rather than beginning 018b automatically.

---

## Focus

> **Understand the existing OpenAI path and choose the smallest next productionization change. Do not build the production system yet.**
