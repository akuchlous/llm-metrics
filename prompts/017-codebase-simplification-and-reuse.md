# Step 017 — Codebase simplification and reuse

## Status

Pending implementation.

## Objective

Reduce the amount of custom code in `llm-metrics` without changing benchmark semantics or public behavior.

This is a cleanup/refactor step, not a feature step.

The primary goals are:

1. identify and eliminate meaningful duplicate code;
2. replace commodity functionality with mature, widely adopted libraries/services where doing so clearly reduces maintenance burden;
3. remove obsolete or unnecessary abstractions and legacy paths that no longer provide value;
4. preserve every measurement invariant established through Step 016;
5. leave the codebase smaller, easier to reason about, and easier for both humans and AI agents to maintain.

The preferred outcome is less custom infrastructure, not merely moving the same amount of complexity into different files.

---

## Required reading

Before changing code, read:

- `CODING_GUIDELINES.md`
- `DECISIONS.md`
- `PROJECT_STATUS.md`
- `prompts/015-output.md`
- `prompts/016-output.md`
- all modules under `llm_metrics/`
- all tests under `tests/`
- `requirements.txt`
- `pyproject.toml`

Understand the current dependency direction and the benchmark semantics before refactoring.

---

## Permanent coding-guideline update

Update `CODING_GUIDELINES.md` with this principle, preserving this wording:

> **Before implementing commodity functionality, search for a mature, widely adopted library/service. Prefer reuse unless it compromises measurement correctness, security, cost, or an important learning objective.**

Place it where it naturally fits the design/architecture guidance.

Also extend the review checklist so future numbered steps explicitly check whether new commodity functionality should be reused rather than implemented locally.

This guideline is a lasting project rule, not Step-017-only advice.

---

## Non-negotiable benchmark invariants

The cleanup must preserve all of these:

- exact canonical workload bytes and workload hashes;
- `interactive-chat-v1` unchanged;
- one benchmark attempt means one provider request;
- no hidden retries;
- no fallbacks;
- no automatic rerouting;
- no provider substitution;
- streaming remains required for TTFT;
- TTFT starts immediately before the provider request and ends only on the first actual generated text;
- metadata, role, heartbeat, usage-only, reasoning-only, thought-only and empty events must not trigger TTFT;
- provider-authoritative token usage remains authoritative;
- unknown remains `None`/SQL `NULL`, never fabricated zero;
- requested output cap and actual output tokens remain separate facts;
- cache policy and provider-reported cached input tokens remain explicit;
- request-profile identity remains explicit and persisted;
- provider request IDs remain captured where available;
- provider/account/setup rejection remains distinct from provider reliability failures;
- failed attempts never acquire fabricated token counts or costs;
- pricing provenance remains auditable;
- prompts, generated responses, API keys and raw provider error bodies are never persisted or logged;
- `./run.sh` remains simulated/offline;
- tests must perform no real network calls;
- imports must perform no network calls;
- no paid provider calls during Step 017.

If a proposed simplification weakens any invariant, do not make that simplification.

---

# Part A — Duplicate-code audit

Before editing, inspect the repository for repeated logic.

At minimum examine:

- provider adapters;
- HTTP request construction;
- streaming/SSE parsing;
- error/status normalization;
- usage validation;
- request-ID extraction;
- safe diagnostic/redaction helpers;
- request-profile checks;
- pricing/cost validation;
- storage row construction;
- query/filter construction;
- formatting helpers;
- CLI argument parsing;
- test fixtures and fake HTTP/stream helpers;
- repeated test assertions;
- repeated documentation/comments that duplicate code rather than explain invariants.

Classify each duplicate pattern as one of:

1. **meaningful duplication** — should be removed;
2. **intentional duplication** — provider/domain differences are clearer when kept separate;
3. **test duplication worth keeping** — independently protects a critical invariant;
4. **incidental similarity** — abstraction would make the code worse.

Do not create a generic abstraction merely because two functions look similar.

Prefer deleting duplication only when the resulting abstraction has a clear current responsibility and makes the code easier to understand.

---

# Part B — Evaluate a mature multi-provider library

The first library candidate to evaluate is **LiteLLM**.

Do not assume it is suitable. Evaluate it against the exact Step 016 benchmark contract.

Use current official LiteLLM documentation/source and current provider documentation as needed.

The evaluation must answer whether LiteLLM can preserve the following for all four selected targets:

- OpenAI `gpt-6-luna`
- Anthropic `claude-haiku-5-5`
- Google `gemini-3.5-flash-lite`
- xAI `grok-4.20-0309-non-reasoning`

For each provider verify:

1. exact model selection;
2. streaming support;
3. ability to preserve exact canonical prompt text;
4. correct output-cap mapping;
5. ability to disable all LiteLLM retries;
6. ability to disable provider-SDK retries if LiteLLM invokes SDKs underneath;
7. no fallback/routing/model substitution;
8. correct first generated text visibility for TTFT;
9. authoritative input tokens;
10. authoritative output tokens;
11. cached-input token visibility, preserving unknown versus zero;
12. provider request-ID visibility where the underlying provider exposes one;
13. cache controls needed by the current request profiles;
14. reasoning/thinking settings needed by the current request profiles;
15. failure/status information sufficient to preserve existing outcome categories;
16. no prompt/response/error-body logging by default in our path;
17. no hidden persistence or telemetry that violates current privacy requirements;
18. ability to use one request per benchmark attempt.

### Decision rule

Prefer LiteLLM if it can preserve measurement correctness and materially reduce custom code.

Do **not** migrate merely because LiteLLM supports the provider.

If LiteLLM hides, rewrites, retries, normalizes away, or makes inaccessible a fact required by LLM Metrics, retain the smallest provider-specific escape hatch necessary.

Allowed end states include:

```text
A. one thin LiteLLM adapter for all four providers

B. LiteLLM for most providers + one or two small provider-specific adapters

C. existing adapters retained because LiteLLM demonstrably compromises measurement fidelity
```

The implementation report must show evidence for the selected end state.

### No proxy/server mode

If LiteLLM is adopted, prefer an in-process Python library call.

Do not introduce the LiteLLM proxy/server, another always-running service, Redis, routing infrastructure, queues, or other operational components in this step.

---

# Part C — Provider-layer simplification

Using the result of Part B, simplify the provider layer as far as safely possible.

Targets:

- remove provider-specific HTTP/SSE parsing that a mature library can correctly own;
- retain LLM Metrics-specific measurement semantics locally;
- retain request-profile definitions locally;
- retain explicit provider/model target registry locally;
- retain explicit pricing provenance locally for now;
- retain outcome categories locally;
- retain benchmark timing locally;
- retain storage/persistence locally;
- retain workload identity locally.

The desired conceptual boundary is:

```text
canonical workload
       ↓
benchmark / measurement logic
       ↓
thin provider boundary
       ↓
LiteLLM or the smallest necessary provider-specific implementation
       ↓
provider API
```

Do not let the provider library become the owner of LLM Metrics' benchmark methodology.

### Retry/fallback safety

If LiteLLM is adopted, tests must prove:

- retry count is zero;
- fallback is absent/disabled;
- routing is absent/disabled;
- one `run_attempt()` causes exactly one provider request;
- provider/model cannot silently change.

---

# Part D — Database/storage reuse assessment

Evaluate whether current hand-written SQLite/storage infrastructure should now move toward **SQLAlchemy** and, if appropriate, **Alembic**.

This part is primarily an architectural assessment unless the migration is clearly small, safe and useful now.

Context:

- local development/tests may continue using SQLite;
- production persistent storage will run on Google Cloud;
- the next infrastructure phase will require a persistent managed database or datastore;
- `storage.py` currently owns schema creation, migration, SQL and SQLite connection handling.

Evaluate:

- SQLAlchemy Core versus ORM;
- portability from SQLite tests to the likely production datastore;
- transaction semantics;
- constraints preserving unknown-versus-zero rules;
- migration safety;
- code reduction versus added abstraction/dependency cost;
- whether Alembic should replace custom `PRAGMA user_version` migration logic before production data exists.

### Important scope boundary

Do not perform a large database migration merely to satisfy Step 017.

If adopting SQLAlchemy/Alembic would make this step risky or too broad, document the recommendation and defer implementation to the Google Cloud persistence step.

The Step 017 report must explicitly say one of:

- `adopted now`, with justification; or
- `recommended for next persistence step`, with justification; or
- `not recommended`, with justification.

---

# Part E — Remove unnecessary code

Look for code that can now be safely removed, including:

- obsolete compatibility paths from earlier steps;
- dead helpers;
- unused constants;
- one-use wrappers that add no semantic value;
- duplicate validation performed at multiple layers without purpose;
- comments/docstrings that narrate implementation history instead of current invariants;
- stale imports/dependencies;
- custom helpers already provided cleanly by Python standard library or an adopted dependency;
- test helpers duplicated across files.

Do not remove backward compatibility that is still required by the current documented behavior or existing database upgrade tests unless the project explicitly no longer needs it.

When uncertain, preserve correctness and document the candidate rather than deleting it.

---

# Part F — Avoid over-abstraction

Cleanup does not mean creating a framework.

Do not introduce:

- generic plugin systems;
- dependency-injection frameworks;
- provider factories with speculative extension points;
- abstract base classes without a concrete need;
- generic repository/service layers merely to hide straightforward SQL;
- event buses;
- registries beyond the current demonstrated need;
- provider-independent configuration schemas that erase real provider differences.

Prefer a small amount of explicit code over a large general-purpose abstraction.

---

# Part G — Measure the cleanup

Record before-and-after code metrics.

At minimum report:

- total Python LOC under `llm_metrics/`;
- provider-layer Python LOC;
- storage-layer Python LOC;
- test Python LOC;
- number of runtime dependencies;
- modules added;
- modules removed;
- meaningful duplicate patterns removed;
- meaningful duplicate patterns intentionally retained.

Use a simple reproducible LOC method and document it.

Do not optimize blindly for the smallest number. The goal is **less maintenance complexity while preserving clarity and correctness**.

A larger dependency may be justified if it deletes substantially more fragile custom infrastructure.

---

# Required tests

Preserve the existing test suite and add focused tests for any changed behavior boundary.

If LiteLLM is adopted, tests must cover at least:

1. canonical prompt forwarded unchanged;
2. exact model id forwarded unchanged;
3. output cap correctly mapped;
4. streaming first-text semantics preserved;
5. metadata/reasoning/empty events do not trigger TTFT;
6. authoritative input/output usage preserved;
7. cached tokens preserve unknown versus zero;
8. provider request ID preserved where available;
9. malformed/incomplete stream normalization;
10. rate-limit normalization;
11. provider/server failure normalization;
12. transport failure normalization;
13. timeout normalization;
14. account/auth/setup rejection not counted as provider reliability;
15. zero retries;
16. zero fallbacks;
17. zero routing/model substitution;
18. exactly one provider request per attempt;
19. no secret/prompt/response/raw error-body leakage;
20. request-profile identity remains stored and enforced.

Existing tests that already prove these facts may be reused or consolidated rather than duplicated.

### Test cleanup

Tests themselves are part of this cleanup.

Consolidate repetitive fixtures/assertions where doing so improves clarity, but do not collapse independent tests for critical measurement semantics into one opaque mega-test.

---

# Compatibility requirements

The following must remain compatible unless the implementation report explicitly identifies a safe internal-only change:

- `benchmark.run_attempt(...)` behavior;
- `LLMProvider` semantics at the measurement boundary;
- existing workload IDs and hashes;
- existing request-profile IDs;
- existing outcome vocabulary;
- existing metric names;
- existing database data semantics;
- HTML dashboard behavior;
- `/api/v1/metrics` behavior;
- `/requests` behavior;
- `/spend` behavior;
- `real_smoke` safety;
- explicit `real_benchmark` one-provider/one-request behavior;
- `./run.sh` offline behavior.

No public JSON shape may change in Step 017 unless absolutely necessary and explicitly documented.

---

# Documentation updates

Update as needed:

- `CODING_GUIDELINES.md`
- `DECISIONS.md`
- `PROJECT_STATUS.md`
- `README.md`
- `llm_metrics/README.md`
- `prompts/chatgpt-conversation.md`

Create:

- `prompts/017-output.md`
- `design-questions/17/` if design questions are materially useful for this refactor.

Do not create documentation merely to repeat code.

---

# `prompts/017-output.md` must include

1. summary of cleanup performed;
2. duplicate-code audit table;
3. LiteLLM evaluation table by provider and measurement requirement;
4. chosen provider-layer architecture and why;
5. exact retry/fallback/routing behavior after cleanup;
6. modules removed/added/merged;
7. before/after LOC measurements;
8. before/after runtime dependencies;
9. meaningful duplicate patterns removed;
10. intentional duplication retained and why;
11. database/storage reuse assessment;
12. SQLAlchemy/Alembic recommendation and timing;
13. tests added/removed/consolidated;
14. final test count and result;
15. formatter/linter results;
16. `./run.sh` result;
17. confirmation that no paid/network provider call was made;
18. confirmation that Step 015 workload hashes remain unchanged;
19. confirmation that request-profile IDs and semantics remain unchanged;
20. known limitations or remaining cleanup candidates.

---

# Explicit non-goals

Do not add:

- paid benchmark runs;
- multi-day experiments;
- Cloud Run;
- Cloud Scheduler;
- production deployment;
- production database creation;
- new workloads;
- new models;
- multiple models per provider;
- quality scoring;
- public rankings;
- retries;
- concurrency/load testing;
- Router functionality;
- Xchange functionality;
- authentication;
- frontend redesign;
- price scraping;
- automated model discovery.

Step 017 should make the current product simpler, not broader.

---

# Stop condition

Before committing:

1. run the complete test suite;
2. run `pyink`, `isort` and `pylint` checks;
3. run `./run.sh`;
4. verify tests and imports make zero real network calls;
5. verify no paid provider calls were made;
6. verify `interactive-chat-v1` and all Step 015 workload hashes are unchanged;
7. verify all four Step 016 request-profile IDs and their semantics remain unchanged;
8. verify retry/fallback/routing behavior is explicit and tested;
9. verify prompts/responses/API keys/raw provider error bodies are neither logged nor persisted;
10. update `prompts/017-output.md` with the actual before/after measurements and decisions;
11. commit and push the Step 017 implementation;
12. stop. Do not begin the paid pilot or Google Cloud deployment.

Report the commit SHA, test count, LOC reduction (or justified increase), dependency changes, provider-library decision, SQLAlchemy/Alembic recommendation, and zero-paid-call confirmation.

## Focus

> **Delete or reuse commodity code while preserving the benchmark's scientific and security semantics.**
