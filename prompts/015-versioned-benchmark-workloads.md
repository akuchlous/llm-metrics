# Step 015 — Define versioned benchmark workloads

## Goal

Move LLM Metrics from infrastructure-first development toward a reproducible benchmark product by defining a small, explicit, versioned workload catalogue that future real-provider comparisons can run consistently.

This step defines **what kind of work is being measured**. It does not yet expand the real-provider set or claim that any workload has been validated by users.

The product principle is:

> Provider/model performance is meaningful only in the context of a defined workload and measurement conditions.

A result should eventually be interpretable as:

```text
provider/model
+ workload definition/version
+ measurement origin
+ cache context
+ time
→ observed latency / throughput / reliability / cost
```

Step 013 already persists `workload_id` on benchmark attempts. Step 015 should make that identity correspond to a real, reproducible, documented workload definition rather than an ad-hoc label.

Keep this step deliberately small. The output should make Step 016 provider expansion and Step 017 provider × model × workload benchmarking straightforward without building a generic benchmark framework.

## Product/research context

User research is running in parallel with engineering. The initial workload catalogue is therefore a set of **benchmark hypotheses**, not a claim that these are the six workloads users value most.

Candidate categories are:

- Interactive Chat
- Coding Assistant
- RAG / Q&A
- Summarization
- Structured Extraction / Classification
- Agent / Tool Use

The catalogue must be easy to extend, version, or deprecate when user research provides better evidence.

Do not encode product recommendations, workload popularity, rankings, or user-demand claims in the implementation.

## Prerequisite / review context

Steps 013 and 014d are complete.

Before editing code, read:

- `CODING_GUIDELINES.md`
- `prompts/013-output.md`
- `prompts/014d-output.md`
- relevant workload/cache/origin decisions in `DECISIONS.md`
- current `PROJECT_STATUS.md`

Understand the existing benchmark orchestration, provider interface, `workload_id` persistence, request facts, and simulated/offline test path before choosing module locations.

## Engineering quality requirement

Follow `CODING_GUIDELINES.md` and Google Python style where appropriate.

Prefer:

- immutable/simple workload definitions;
- explicit versioned identities;
- deterministic benchmark inputs;
- one obvious catalogue owner;
- validation that makes invalid definitions difficult to introduce;
- small functions and data structures;
- comments/docstrings that explain measurement semantics and invariants;
- tests that protect reproducibility.

Avoid:

- a generic workload DSL;
- plugin systems;
- YAML/config frameworks merely for extensibility;
- provider-specific workload subclasses;
- factories/registries with speculative extension points;
- prompt-generation frameworks;
- quality/evaluation frameworks;
- dependencies added only to represent static workload definitions.

Passing tests is necessary but not sufficient. Review the changed code for measurement integrity, reproducibility, and future readability before committing.

## Core workload contract

Create the smallest sensible framework-independent representation for a benchmark workload.

A workload definition should contain concepts equivalent to:

```text
workload_id
category
version
human-readable name/description
benchmark input/instructions
requested maximum output tokens
```

The exact Python shape is an implementation decision. A frozen dataclass or similarly simple immutable structure is preferred if it fits the current code.

The stable external identity should be explicit and versioned, for example:

```text
interactive-chat-v1
coding-v1
rag-v1
summarization-v1
extraction-v1
agent-tool-v1
```

Do not make callers construct IDs by concatenating category/version independently if a single canonical identity is clearer.

### Version semantics

Treat the workload ID/version as part of measurement identity.

If a future change materially alters the benchmark input, instructions, task semantics, or requested output cap such that measurements are no longer directly comparable, create a new workload version rather than silently changing the old definition.

Examples:

```text
rag-v1 -> rag-v2
coding-v1 -> coding-v2
```

Do not build migration/deprecation machinery now. Document the compatibility principle.

## Initial candidate catalogue

Define six initial candidate workloads representing substantially different application shapes:

| Workload ID | Category | Approximate input shape | Output cap | Intended application |
|---|---|---:|---:|---|
| `interactive-chat-v1` | interactive_chat | ~2K tokens | 300 | conversational assistant |
| `coding-v1` | coding | ~8K tokens | 1000 | code generation/debugging |
| `rag-v1` | rag | ~16K tokens | 500 | answer using supplied context |
| `summarization-v1` | summarization | ~32K tokens | 1000 | long-document summarization |
| `extraction-v1` | extraction | ~4K tokens | 150 | structured extraction/classification |
| `agent-tool-v1` | agent_tool | ~8K tokens | 300 | reasoning/tool-selection style task |

These sizes are approximate design targets, not promises of identical token counts across providers.

If constructing all six full-size deterministic inputs would materially bloat the repository or make this step unnecessarily expensive/complex, keep the representation and catalogue complete but choose the smallest deterministic fixture strategy that preserves the intended workload shapes. Explain the tradeoff in `015-output.md`.

Do not introduce huge copyrighted corpora or externally downloaded benchmark datasets.

Use synthetic/original deterministic benchmark material that can safely live in the repository.

## Critical fairness rule: same input, provider-specific token counts

Do **not** define fairness as every provider receiving exactly the same number of input tokens.

Different providers/models may tokenize the same text differently and may apply different request templates/protocol overhead.

For a workload version, preserve the same benchmark content/task semantics across providers. Then record provider-authoritative input/output token usage when available.

Conceptually:

```text
same workload definition/input
        |
        +--> provider A -> observed input token count A
        +--> provider B -> observed input token count B
        +--> provider C -> observed input token count C
```

Those token-count differences are facts, not errors to normalize away.

Do not add provider tokenizer dependencies merely to force inputs to exact token lengths.

Approximate input-size targets may be generated/validated using deterministic text characteristics or an existing tokenizer only if already appropriate, but provider-authoritative usage remains the measurement fact once a real request runs.

Document this explicitly in methodology/decisions.

## Output-size semantics

`requested_max_output_tokens` is a **cap**, not a promise that a model will emit exactly that many tokens.

Do not retry a request until it reaches the target output length.

Preserve the existing distinction between:

```text
requested maximum output tokens
actual provider-reported output tokens
```

The actual output token count remains the observed fact used for throughput/cost interpretation.

Do not introduce minimum-output enforcement or repeated generation in this step.

## Deterministic inputs

A workload version must be reproducible.

Running `rag-v1` tomorrow should mean the same benchmark task/content unless a new version is intentionally created.

Avoid:

- timestamps in workload prompts;
- random prompt generation;
- network-fetched source text;
- mutable external URLs as benchmark content;
- environment-dependent content;
- provider-specific wording unless the provider protocol requires a semantically neutral wrapper outside the workload definition.

Tests should be able to prove catalogue inputs are deterministic without network access.

If large repeated filler/context is generated programmatically, generation must itself be deterministic and obvious, and the canonical workload semantics must remain inspectable by a human reviewer.

## Workload content design

Each workload should resemble its intended application enough to produce meaningfully different request shapes, but Step 015 is a performance-workload definition step, not a quality benchmark.

Examples of acceptable task shapes:

### Interactive chat

A concise conversational/system context plus a user question requiring a moderately sized explanatory response.

### Coding

A deterministic source-code/problem context and a request to implement, debug, explain, or modify code.

### RAG / Q&A

A deterministic supplied context plus a question that instructs the model to answer using that context.

### Summarization

A deterministic long document-like input plus a request for a structured summary.

### Extraction / classification

A deterministic semi-structured document plus explicit fields/categories to extract, preferably requesting a predictable textual/JSON-like shape without adding a cross-provider structured-output dependency in this step.

### Agent / tool use

A deterministic task that resembles deciding among tools/actions or planning a tool-oriented next step. Do not require actual provider-native tool/function calling yet unless the existing provider abstraction already supports it uniformly. The workload may represent the reasoning/selection shape in plain text for v1.

The objective is controlled performance measurement, not proving answer correctness.

## Catalogue ownership and lookup

Create one obvious owner for workload definitions, likely a small module such as `llm_metrics/workloads.py` if that fits the repository.

Provide the smallest useful operations needed by the benchmark path, such as:

```text
get_workload(workload_id)
list_workloads()
```

or equivalent.

Unknown workload IDs should fail clearly before any paid provider request begins.

Do not add database tables for workload definitions in this step. Workload versions are code-defined benchmark methodology for now.

Do not make workload definitions editable through the web UI/API.

## Integrate with benchmark orchestration

Update the benchmark path so a benchmark can select a canonical workload definition rather than independently supplying an arbitrary workload label plus unrelated prompt/output cap.

Preserve the current separation of responsibilities:

```text
workload catalogue -> benchmark orchestration -> measurement/provider -> persistence
```

The workload catalogue owns reproducible workload definition.

The benchmark/orchestration layer owns executing a selected workload.

Provider modules own provider protocol translation.

Measurement owns timing/usage facts.

Storage owns persisted facts.

Do not allow workload definitions to import provider implementations, Flask, storage, analytics, or dashboard code.

### Compatibility with existing callers/tests

Make the smallest coherent change to existing benchmark APIs.

If existing tests or CLI paths currently pass raw prompts/workload IDs directly, migrate them deliberately rather than creating a confusing permanent dual model solely to avoid edits.

However, preserve the existing simulated/offline developer workflow and real OpenAI smoke-test safety constraints.

No normal test or `./run.sh` path may make a paid call.

## CLI / developer experience

Expose workload selection through the existing benchmark CLI/developer path in the simplest consistent way.

A developer should be able to identify which canonical workload is being run.

If a workload argument is added, validate it before provider/network execution and provide a concise safe error listing valid workload IDs.

Do not redesign the CLI broadly.

The default simulated `./run.sh` path should remain deterministic and fast. It does not need to execute all six large workloads on every local run if that would slow the developer loop materially. Choose a representative default and test the full catalogue separately/offline.

## Persistence

Continue storing the canonical versioned workload ID in the existing `workload_id` request fact.

Do not duplicate the entire prompt/input into the database.

Do not store prompts or generated responses merely for benchmark traceability.

The code-defined versioned workload identity is the link back to benchmark methodology.

No schema migration should be necessary unless the actual current schema reveals a concrete need. Avoid adding one speculatively.

## API/dashboard scope

Do not redesign `/api/v1/metrics` or the HTML dashboard in this step merely to expose the catalogue.

A future step can add workload/provider/model selectors once real multi-provider population semantics are ready.

If tiny documentation changes are needed to explain that current aggregate views remain simulated/fixed-population, make them, but do not expand the public endpoint family.

## Security / privacy / licensing

Benchmark inputs committed to the repository must be safe to publish.

Do not include:

- secrets or credentials;
- personal/private user data;
- proprietary Google/internal material;
- copied customer prompts;
- copyrighted long-form material without appropriate rights;
- raw content from user interviews;
- malicious payloads that would create unnecessary execution/security risk.

Prefer original synthetic content written specifically for the benchmark.

The benchmark runner must never log API keys or provider secrets.

Preserve existing prompt/response privacy constraints for persisted/logged request data.

## Tests

Add focused tests covering at least:

1. all six canonical workload IDs exist;
2. workload IDs are unique and explicitly versioned;
3. categories/versions/names/descriptions are non-empty and coherent;
4. requested maximum output tokens are positive and match the documented catalogue;
5. benchmark inputs are non-empty and deterministic;
6. catalogue lookup returns the canonical definition;
7. unknown workload lookup fails clearly before provider/network execution;
8. benchmark orchestration uses the selected workload's canonical ID, input, and output cap;
9. the persisted request fact contains the canonical versioned workload ID;
10. actual provider-reported input/output token facts remain distinct from approximate workload size targets;
11. actual output tokens remain distinct from requested maximum output tokens;
12. no retry/minimum-output behavior is introduced to force exact output length;
13. workload definitions have no dependency on Flask/Jinja/dashboard/API/storage/provider implementations;
14. existing OpenAI real-call safety/explicit opt-in remains intact;
15. no tests make network or paid provider calls;
16. `./run.sh` remains deterministic/offline and working;
17. existing API/dashboard behavior remains compatible unless a narrowly documented change is required;
18. formatting/style/dependency-direction checks remain clean.

Add any additional tests needed to protect workload-version compatibility and deterministic content.

Do not weaken existing assertions to make Step 015 pass.

## Documentation / methodology

Update `DECISIONS.md` with at least these principles:

- workload identity is versioned and part of the measurement population;
- material workload changes require a new workload version;
- fairness means reproducible equivalent workload content/semantics, not forced identical token counts across provider tokenizers;
- provider-authoritative actual token counts remain observed facts;
- requested output size is a cap, not a guaranteed generated length;
- the initial six workloads are candidate benchmark hypotheses subject to user-research refinement.

Update `PROJECT_STATUS.md` to current truth.

Update relevant README/methodology documentation so a future contributor can understand:

- what each workload represents;
- approximate intended input shape;
- output cap;
- how versioning works;
- why token counts may differ by provider;
- that these are performance workloads, not quality claims.

Create:

`prompts/015-output.md`

The implementation report should include:

- files/modules changed;
- final workload representation and catalogue;
- exact six workload IDs/categories/output caps;
- how deterministic input content is constructed/stored;
- actual approximate input sizes achieved by the fixtures using whatever non-provider-specific measurement is available, while clearly labeling that as approximate rather than provider-authoritative;
- benchmark/CLI integration;
- dependency direction;
- versioning/fairness semantics;
- tests/style results;
- whether any paid/network calls occurred;
- known limitations;
- what Step 016 can now rely on.

Create role-specific design-question material under `design-questions/15/` following the existing workflow.

Update `prompts/chatgpt-conversation.md` with the durable Step 015 direction and the standing product/growth workflow:

- user research runs in parallel and does not unnecessarily block engineering;
- initial workloads are hypotheses subject to evidence;
- at every meaningful engineering milestone, run a MARKETING CHECKPOINT;
- approximately 30% of the overall effort is Build/Learn and 70% Grow/Distribute;
- a checkpoint may conclude `do not publish yet`;
- when there is a publishable finding, user-research opportunity, or growth task, prepare a short handoff containing milestone, evidence/sample size, limitations, relevant links, and suggested growth opportunity.

Do not modify prior numbered prompts.

## Marketing checkpoint deliverable

Step 015 itself is engineering, but its output may create a useful methodology story.

At the end of the implementation report, add a short factual section titled:

```text
## Marketing checkpoint inputs
```

This is **not** marketing copy and Claude should not decide whether to publish.

Include only evidence that ChatGPT/the Growth workstream can use to make that decision:

- milestone completed;
- exact workload catalogue;
- reproducibility/versioning decisions;
- any measured fixture sizes/sample facts available from the implementation;
- test count/status;
- limitations, especially that workloads are hypotheses and broad real-provider comparison data does not yet exist;
- repository paths/commit SHA relevant to the milestone;
- one or two technically interesting observations discovered during implementation, if any.

Do not fabricate an insight merely to make the milestone marketable.

## Scope exclusions

Do **not** in Step 015:

- add Anthropic, Google, xAI/Grok, or other providers;
- add additional real OpenAI models solely for comparison;
- run a provider comparison matrix;
- make paid benchmark calls;
- add quality scoring/evaluation;
- add LLM-as-judge;
- add recommendation/ranking logic;
- claim one workload/provider/model is best;
- add provider-specific tokenizers merely to normalize token counts;
- retry until exact output length;
- add native tool/function-calling abstractions solely for `agent-tool-v1`;
- add a generic benchmark DSL/plugin system;
- add database-managed workload definitions;
- add workload editing UI/API;
- add provider/model/workload selectors to `/api/v1/metrics`;
- add scheduling/Cloud Run jobs;
- add PostgreSQL/SQLAlchemy;
- add deployment/cloud infrastructure;
- add growth analytics tooling;
- add Router or Exchange functionality;
- add automated social publishing;
- store prompts/responses in request history;
- use private/proprietary/copyright-problematic benchmark corpora.

## Stop condition

Run the complete test suite, formatting/style checks, dependency/layering checks, and `./run.sh` simulated path.

Before committing, review the implementation as if Step 016 were going to add Anthropic, Google, and xAI adapters tomorrow.

A future provider adapter should not need to redefine what `rag-v1` or `coding-v1` means. It should receive the canonical workload content/output cap through the benchmark/orchestration path and report provider-authoritative usage/measurement facts back through the existing measurement model.

Also review the catalogue as if user research next week said that one workload is unimportant and another needs a substantially different shape. The design should allow adding/deprecating/versioning workloads without rewriting provider, storage, analytics, or web layers.

Commit and push Step 015, then stop.

Do not begin provider expansion or Step 016.

Report:

- commit SHA;
- workload IDs and output caps;
- module/dependency shape;
- benchmark/CLI integration;
- test count and style/dependency results;
- whether any network/paid calls occurred;
- known limitations;
- `Marketing checkpoint inputs` summary.