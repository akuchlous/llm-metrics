# Step 016 — Four-provider benchmark adapters

## Goal

Extend LLM Metrics from one real provider to a minimal **four-provider benchmark capability**:

- OpenAI
- Anthropic
- Google
- xAI

Implement exactly **one deliberately selected real model per provider** so that the canonical `interactive-chat-v1` workload from Step 015 can eventually be measured across all four providers using the same benchmark pipeline.

This step establishes provider correctness and comparability.

It is **not** the seven-day benchmark experiment yet.

Do not add scheduling, batch execution, experiment orchestration, production deployment, or broad model catalogues in this step.

The target architecture remains:

```text
canonical workload
       ↓
benchmark.run_attempt(...)
       ↓
LLMProvider interface
       ↓
┌────────────┬────────────┬────────────┬────────────┐
│ OpenAI     │ Anthropic  │ Google     │ xAI       │
│ adapter    │ adapter    │ adapter    │ adapter    │
└────────────┴────────────┴────────────┴────────────┘
       ↓
normalized measurement facts
       ↓
existing persistence
```

Every provider receives the same canonical workload content.

Provider adapters may translate that workload into the provider's required API request shape, but they must not alter the benchmark's semantic content.

## Context

Steps through 015 are complete.

Step 015 introduced versioned canonical workloads in `llm_metrics/workloads.py`.

The initial real comparison workload is `interactive-chat-v1`, approximately 2,000 input tokens with `max_output_tokens = 300`.

The workload content, instructions and output cap are versioned benchmark identity and must not be modified in Step 016.

`benchmark.run_attempt(...)` accepts a canonical `Workload` and stores its `workload_id`.

Providers continue to receive only the provider-neutral request concepts they actually require.

The existing OpenAI real-provider implementation and real smoke path should be treated as the starting reference, not automatically copied architecturally if another provider has different semantics.

Before editing code, read at least:

- `CODING_GUIDELINES.md`
- `DECISIONS.md`
- `PROJECT_STATUS.md`
- `prompts/015-output.md`
- `llm_metrics/workloads.py`
- `llm_metrics/benchmark.py`
- `llm_metrics/providers.py`
- `llm_metrics/openai_provider.py`
- `llm_metrics/latency.py`
- `llm_metrics/pricing.py`
- `llm_metrics/storage.py`

Also inspect the existing provider tests before designing new adapters.

## Engineering quality requirement

Follow `CODING_GUIDELINES.md` and Google Python style where appropriate.

Priorities remain:

1. correctness and measurement integrity;
2. security/privacy;
3. readability and maintainability;
4. explicit provider semantics;
5. consistency with existing repository contracts;
6. minimal implementation.

Prefer clear provider-specific code over an abstraction that hides meaningful API differences.

Do not introduce a generic provider SDK/framework simply because four adapters now exist.

Extract shared code only when there is genuinely identical behavior whose ownership becomes clearer by sharing it.

Provider differences are data we need to understand, not complexity we should automatically abstract away.

## Product objective

We are preparing a controlled seven-day benchmark experiment.

The intended later experiment is approximately:

```text
1 canonical workload
×
4 providers
×
1 model/provider
×
10 attempts/window
×
4 windows/day
×
7 days

= 1,120 benchmark attempts
```

Step 016 does **not** run that experiment.

Step 016 must make it possible to safely perform the small paid pilot that precedes it.

The immediate product question is:

> Can LLM Metrics make one semantically consistent interactive-chat request to each provider and record comparable, provider-authoritative measurement facts without hiding meaningful differences?

## Provider/model selection

Implement exactly one real benchmark target for each provider:

- OpenAI
- Anthropic
- Google
- xAI

Choose one current, generally available API model from each provider that is reasonably appropriate for an interactive application benchmark.

Do not create a broad model catalogue.

Do not select models solely because their names appear similar.

The purpose is not to claim four models have identical capability or quality.

The purpose is to establish a useful initial performance/cost/reliability comparison under one reproducible workload.

### Verify current model/API facts

Provider model names, endpoints, streaming semantics, usage reporting, pricing and request options can change.

Before finalizing each adapter, verify current facts against the provider's official documentation.

Document the selected model IDs and the official source used to verify:

- model availability;
- API endpoint/protocol;
- streaming behavior;
- token usage reporting;
- relevant reasoning/thinking controls;
- cache controls or cache reporting;
- pricing.

Do not rely solely on memory, third-party blog posts or model-name assumptions.

Do not silently substitute another model when the configured model is unavailable.

If a model-selection question is genuinely ambiguous, document the alternatives and choose the smallest defensible option for the pilot.

## Provider-neutral interface

Preserve the existing provider boundary where practical.

A provider adapter should continue to expose the benchmark concepts required by the existing measurement layer rather than leaking provider-specific HTTP response objects upward.

Do not redesign the entire provider interface unless a concrete incompatibility makes a small change necessary.

If the interface must change, explain:

- why the current contract is insufficient;
- the smallest new concept required;
- why the concept belongs in the provider-neutral layer;
- how existing dummy/OpenAI behavior remains compatible.

Provider adapters should normalize protocol differences.

They should **not normalize away factual differences** such as token counts or cache usage.

## Exact workload semantics

For the benchmark target use `interactive-chat-v1`.

Every provider must receive the exact canonical workload text from `workloads.py`.

Do not:

- rewrite the prompt per provider;
- shorten it;
- add provider-specific benchmark instructions;
- add hidden system prompts;
- remove sections;
- translate it;
- add provider branding;
- change the requested output cap.

If an API requires a message/content wrapper, wrap the canonical text in the smallest semantically neutral request representation.

Changing protocol representation is acceptable. Changing semantic input is not.

## Request profiles are measurement conditions

Step 015 identified an important limitation: provider request settings such as reasoning effort, thinking mode, caching behavior and other adapter-level controls currently exist outside `workload_id`.

Do not incorrectly put provider-specific request settings into the workload identity.

Instead, Step 016 must make the effective provider request configuration explicit and auditable.

Introduce the smallest representation needed to answer:

> Under what provider request configuration was this measurement made?

Call this concept something clear such as a **request profile** if that fits the existing architecture.

Avoid a generic configuration framework.

The profile should identify benchmark-relevant settings that can materially affect performance, cost or comparability. Examples may include:

- provider;
- model;
- reasoning/thinking setting;
- cache policy;
- temperature or equivalent if explicitly set;
- other material generation controls.

Only record settings we deliberately control or can truthfully identify.

Unknown remains unknown.

Do not fabricate equivalence across provider controls.

For example, `OpenAI reasoning=none` does not imply another provider has an exactly equivalent setting.

Document provider differences explicitly.

The profile must be stable enough that later seven-day measurements do not silently mix requests made under different material configurations.

Do not build a general configuration/versioning service.

A small explicit immutable representation is preferable.

## Reasoning / thinking behavior

Interactive latency comparisons can become misleading if one provider performs substantial hidden reasoning while another does not.

For each selected model:

1. determine whether reasoning/thinking is mandatory, optional, configurable or not applicable;
2. use the lowest/default non-reasoning configuration appropriate for ordinary interactive use where the provider supports such a choice;
3. record/document the effective choice;
4. do not claim two provider settings are semantically identical unless the providers actually define them that way.

If reasoning cannot be disabled, preserve that fact as part of the benchmark methodology.

Do not manipulate prompts to suppress reasoning.

## Sampling parameters

Avoid unnecessary provider-specific sampling differences.

If temperature or similar sampling parameters do not need to be specified, prefer provider defaults unless there is a strong comparability reason to set them explicitly.

If a parameter is explicitly controlled, make it part of the documented request profile.

Do not invent unsupported cross-provider parameter mappings.

The benchmark is primarily measuring provider/model behavior under a controlled workload, not trying to force every internal generation mechanism to be identical.

## Streaming requirement

The benchmark requires streaming because TTFT is a core measurement.

Each real provider adapter must use the provider's supported streaming mechanism.

Correctly identify:

- request start;
- first actual generated output content;
- stream completion;
- authoritative usage information;
- provider request identifier where available.

Do not treat protocol metadata, role events, empty deltas, heartbeat events, usage-only events or other non-output events as first generated content.

TTFT must continue to mean the existing measurement definition used by LLM Metrics.

If a provider's protocol makes TTFT semantics materially different, document the limitation rather than hiding it.

## Usage accounting

Prefer provider-authoritative usage.

For successful attempts, capture provider-reported facts where available:

- `input_tokens`
- `output_tokens`
- `cached_input_tokens`

Preserve existing unknown-versus-zero semantics.

`cached_input_tokens = 0` means the provider explicitly reported zero cached input tokens.

`cached_input_tokens = NULL` means unknown/not reported/not applicable.

Do not estimate provider token counts from characters when authoritative usage exists.

Do not substitute the Step 015 `target_input_tokens` estimate for provider usage.

Different providers are expected to report different input token counts for the same canonical text. That difference is valid benchmark data.

## Output token cap

Use the workload's canonical `max_output_tokens = 300`.

Translate that into the correct provider-specific API field.

Do not retry because a provider produces fewer than 300 tokens.

Do not request continuation.

Do not attempt to force identical actual output lengths.

Preserve `requested_max_output_tokens` and actual `output_tokens` as separate facts.

The output cap is a maximum, not a target.

## Cache behavior

Use the most defensible cache policy for a controlled first benchmark.

Prefer explicitly uncached behavior where the provider offers a documented way to request it without materially changing workload semantics.

Where explicit cache control is unavailable, use provider-default behavior and record that fact.

Where cached-input usage is authoritatively reported, persist it.

Do not infer caching from latency.

Do not call a measurement "cold" unless the methodology actually establishes the relevant cache state.

Prefer existing terminology:

- explicitly uncached / cold-ish;
- provider-default;
- cached/warm where authoritatively observed;
- unknown.

Do not silently aggregate materially different cache policies later.

## Pricing

Extend the existing pricing source only as needed for the four selected models.

Use verified official provider pricing.

Record the effective input and output rates used for each request using the existing pricing semantics.

If a provider has distinct cached-input pricing and the benchmark can observe/apply it correctly, document whether Step 016 supports it.

Do not silently charge normal input pricing to cached tokens if the provider's billing semantics materially differ and we know they were cached.

If correct cached pricing would require substantial new machinery, keep the pilot configuration uncached where possible and document the limitation.

Do not add automated price scraping, price-history services, dynamic pricing discovery, or broad model pricing catalogues.

## Provider request IDs

Capture provider-authoritative request IDs where available.

Preserve the existing distinction: the LLM Metrics `request_id` is our attempt identity; `provider_request_id` is external diagnostic metadata.

Do not use provider request IDs as primary database identity.

If a provider does not expose a usable request ID through the API path, store unknown rather than inventing one.

## Failure normalization

Map provider-specific failures into the existing normalized categories where appropriate:

- timeout;
- rate_limited;
- provider_error;
- transport_error;
- invalid_response.

Preserve existing semantics.

Do not store raw provider error bodies.

Do not leak API keys, prompts, generated responses, raw HTTP bodies, stack traces, or secrets.

Sanitized diagnostics may contain only information needed to understand the failure safely.

Account/billing/configuration failures that are clearly our own benchmark setup problem must not be misrepresented as evidence of provider unreliability.

Follow the existing OpenAI precedent where applicable.

Do not automatically retry benchmark attempts.

## HTTP implementation

Prefer the Python standard library if consistent with the existing provider implementation and reasonably maintainable.

Do not add four large provider SDKs merely for convenience unless there is a concrete correctness or maintenance reason.

If a provider's official protocol is sufficiently complex that using its maintained SDK is materially safer, document the trade-off before adding the dependency.

Avoid dependency growth where a small explicit streaming HTTP implementation is understandable and testable.

Provider-specific protocol parsing should remain isolated inside the adapter.

## Secrets

Use environment variables for provider credentials.

Use clear provider-specific names, for example the provider's conventional API-key environment variable.

Never commit credentials, put them in workload definitions, store them in SQLite, print them, include them in exceptions, or include them in output reports.

Missing credentials must fail clearly before a paid/network request.

Tests must not require real credentials.

## Real benchmark execution safety

Step 016 adds capability.

It must **not accidentally turn normal development commands into paid multi-provider benchmark calls.**

Requirements:

- `./run.sh` remains offline/simulated.
- automated tests make no real network calls.
- importing provider modules makes no network calls.
- importing workload modules makes no network calls.
- real provider execution requires explicit user action.
- no command should automatically iterate all four paid providers merely because credentials are present.
- do not run `interactive-chat-v1` against real providers as part of tests.

A later Step 016a performs the explicit paid pilot.

## Minimal manual validation path

Provide a deliberate manual command/path capable of running one provider × one canonical workload × one attempt for the later pilot.

The operator must explicitly choose the provider.

A conceptual CLI shape is:

```text
python -m ... --provider anthropic --workload interactive-chat-v1 --real
```

The exact CLI shape should fit the existing repository rather than blindly following this example.

Safety matters more than CLI aesthetics.

Before the request begins, print only safe benchmark metadata such as provider, model, workload ID, output cap, origin, and estimated/request pricing basis if available.

Do not print the prompt.

Do not print credentials.

Do not print generated response content merely for debugging.

## Selected-target registry

Create the smallest obvious source of truth for the four benchmark targets.

Conceptually:

```text
openai
  model: ...

anthropic
  model: ...

google
  model: ...

xai
  model: ...
```

Do not scatter selected model IDs throughout tests, CLI code, adapters and pricing code.

However, do not build a generic provider registry framework if a small constant/dataclass mapping is sufficient.

The selected target should make it obvious which exact model participates in the initial four-provider experiment.

## Tests

Add focused tests covering at least the following.

### Provider adapters

For every real provider:

1. canonical workload text reaches the adapter unchanged;
2. workload output cap maps to the correct provider request field;
3. streaming content is parsed correctly;
4. protocol metadata before actual output does not incorrectly trigger first-token measurement;
5. authoritative input/output usage is captured;
6. cached input usage preserves unknown versus reported zero where supported;
7. provider request ID is captured where available;
8. malformed/incomplete streams become the correct normalized failure;
9. rate limits are normalized correctly;
10. provider/server errors are normalized correctly;
11. transport failures are normalized correctly;
12. timeouts are normalized correctly;
13. secrets/raw provider errors are not persisted or printed.

Use representative mocked protocol fixtures.

Do not call real provider APIs.

### Request profiles

Test that:

14. each selected target has one explicit benchmark request profile;
15. provider/model/profile facts cannot silently change inside a measurement population;
16. unknown settings remain unknown rather than becoming fabricated defaults;
17. workload identity remains separate from provider request profile;
18. provider-specific reasoning/cache differences remain explicit.

### Usage / cost

Test that:

19. provider-authoritative token counts are stored unchanged;
20. different providers may report different input token counts for the same workload;
21. actual output tokens remain separate from the output cap;
22. cost uses the correct verified selected-model rates;
23. unknown usage does not become zero cost unless zero is genuinely known;
24. effective pricing basis remains auditable.

### Safety

Test that:

25. missing credentials fail before network access;
26. invalid provider selection fails before network access;
27. `./run.sh` remains simulated/offline;
28. the full automated test suite performs no paid/network calls;
29. prompts and generated responses are not stored;
30. provider modules have no import-time network behavior.

### Compatibility

Test that:

31. the dummy provider continues to work;
32. existing OpenAI smoke behavior remains safe;
33. existing request persistence semantics remain valid;
34. existing dashboard/API behavior is not unintentionally changed;
35. Step 015 workload hashes/content remain unchanged;
36. `interactive-chat-v1` remains canonical and immutable.

Do not weaken existing tests.

## Documentation

Update:

- `DECISIONS.md`
- `PROJECT_STATUS.md`
- `README.md`
- `llm_metrics/README.md`
- `prompts/chatgpt-conversation.md`

Document:

- the four selected providers/models;
- why each model was selected;
- official documentation/pricing sources;
- exact request-profile settings;
- reasoning/thinking configuration;
- cache policy;
- streaming/TTFT semantics;
- usage semantics;
- pricing semantics;
- known cross-provider differences;
- limitations of claiming comparability.

Create `prompts/016-output.md`.

The implementation report must include:

1. files/modules changed;
2. selected provider/model table;
3. exact model IDs;
4. request-profile table;
5. API endpoint/protocol used per provider;
6. streaming event mapping per provider;
7. usage mapping per provider;
8. request-ID mapping;
9. cache semantics;
10. reasoning/thinking semantics;
11. pricing and source provenance;
12. failure normalization;
13. dependency changes;
14. test/style results;
15. explicit confirmation that no paid API call was made by automated implementation/tests;
16. known limitations;
17. exact manual commands intended for Step 016a pilot.

Create/update role-specific design questions under `design-questions/16/` following the existing workflow.

Do not modify previous numbered prompts.

## Important comparability statement

Document prominently:

> The four-provider benchmark controls workload content, workload version, output cap, measurement origin and known request settings. It does not establish that the selected models have identical capability, tokenizer behavior, internal architecture, reasoning implementation, caching implementation or service infrastructure.

Performance results therefore describe:

> observed behavior of these exact provider/model/request-profile combinations under this benchmark methodology.

They are not universal provider performance claims.

## Scope exclusions

Do **not** in Step 016:

- run the seven-day experiment;
- run 1,120 requests;
- perform the paid four-provider pilot automatically;
- add scheduling;
- add cron;
- add Cloud Scheduler;
- add Cloud Run Jobs;
- deploy the website;
- add PostgreSQL;
- add experiment/batch orchestration;
- add attempt-number/window tracking;
- add retries;
- add concurrency/load testing;
- add multiple models/provider;
- add quality scoring;
- rank providers;
- recommend a winner;
- add workload-specific public rankings;
- add user authentication;
- add API keys for LLM Metrics users;
- add Router/Xchange functionality;
- add automated price scraping;
- add broad model discovery;
- redesign the website;
- add frontend frameworks;
- change Step 015 workload content.

Keep Step 016 narrowly focused on:

> **four correct real-provider adapters + one explicit benchmark target/profile per provider.**

## Stop condition

Run:

- the complete automated test suite;
- formatting/style checks;
- dependency/layering checks;
- `./run.sh`.

Review the implementation against `CODING_GUIDELINES.md`.

Verify that automated tests made **zero real provider calls**.

Verify that `interactive-chat-v1` is byte-for-byte unchanged from Step 015.

Verify that each selected model and pricing entry is supported by current official provider documentation.

Verify that a future operator can clearly answer:

- Which exact model was called?
- Which exact workload was sent?
- Which request settings were used?
- Was reasoning/thinking enabled?
- What was the cache policy?
- What output cap was requested?
- Which token counts came from the provider?
- How was TTFT determined?
- Which pricing rates were applied?
- Which provider request ID was returned?

Commit and push Step 016.

Then stop.

Do **not** begin Step 016a or make paid pilot calls.

Report:

- commit SHA;
- four selected models;
- provider/request-profile summary;
- test count;
- style result;
- confirmation of zero paid calls;
- known limitations;
- exact manual pilot commands.

After Step 016, return the result to ChatGPT for review before any paid pilot begins.

The next intended milestone is:

```text
Step 016a — small paid four-provider pilot
```

followed by a mandatory:

```text
🟠 MARKETING CHECKPOINT
```
