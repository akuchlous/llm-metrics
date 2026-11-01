# Step 018 — Guided four-provider live pilot

## Status

Pending execution.

## Objective

Validate the real provider integrations from Steps 016–017 against live APIs with a very small, explicitly user-driven paid pilot.

This is **not** a benchmark study and must not produce provider performance conclusions. The purpose is to verify that the live APIs still match our protocol assumptions and that one real request per provider flows correctly through streaming, TTFT, usage normalization, pricing, and persistence.

Targets:

- OpenAI — `gpt-6-luna`
- Anthropic — `claude-haiku-5-5`
- Google — `gemini-3.5-flash-lite`
- xAI — `grok-4.20-0309-non-reasoning`

Default workload: `interactive-chat-v1`.

---

## REQUIRED OPERATING MODE — GUIDE THE USER ONE STEP AT A TIME

Claude must **not** make paid provider calls itself.

Claude must guide the user interactively, one provider at a time.

For each provider:

1. verify the account/API access prerequisites;
2. help the user create or verify the developer/API account if needed;
3. help the user enable billing/credits/model access if required;
4. help the user create an API key;
5. tell the user how to store the key safely in the shell using an environment variable;
6. never ask the user to paste the actual key into chat;
7. give exactly one live command;
8. ask the user to paste only the safe command output back;
9. inspect the result before giving the next provider's instructions;
10. if a defect is found, stop further paid calls, diagnose it, and make the smallest justified fix/test before retrying.

Do **not** dump all four provider commands at once unless the user explicitly asks.

The normal cadence is:

```text
account/access setup
→ create key
→ export key locally
→ one paid request
→ inspect result
→ next provider
```

---

## Account and API-key setup guidance

Claude should actively help the user obtain working API credentials for each provider.

For each provider, explain the current minimum setup path using current official provider documentation/pages where practical:

- where to sign in or create the developer/API account;
- whether a separate developer console/project/workspace is required;
- how to enable API billing or add credits if required;
- how to confirm the selected benchmark model is available to the account;
- where to create a new API key;
- which local environment variable to use;
- how to verify that the variable is set **without printing the secret**.

Provider environment variables:

- OpenAI: `OPENAI_API_KEY`
- Anthropic: `ANTHROPIC_API_KEY`
- Google: `GEMINI_API_KEY`
- xAI: `XAI_API_KEY`

Show placeholders only, e.g.:

```bash
export OPENAI_API_KEY='YOUR_KEY_HERE'
```

Safe verification example:

```bash
python - <<'PY'
import os
print('set' if os.environ.get('OPENAI_API_KEY') else 'missing')
PY
```

Never ask the user to paste:

- API keys;
- passwords;
- MFA codes;
- billing/card details;
- recovery codes;
- session cookies;
- account tokens.

The user must personally handle login, MFA, payment details, acceptance of provider terms, and copying the key into their own shell.

If a provider requires browser/UI actions, Claude should give the exact current navigation steps and then wait for the user to complete them.

---

## Required reading before the first live call

Read:

- `CODING_GUIDELINES.md`
- `DECISIONS.md`
- `PROJECT_STATUS.md`
- `prompts/016-output.md`
- `prompts/017-output.md`
- `llm_metrics/targets.py`
- `llm_metrics/real_benchmark.py`
- `llm_metrics/benchmark.py`
- `llm_metrics/latency.py`
- `llm_metrics/pricing.py`
- `llm_metrics/storage.py`
- all four provider adapters
- the relevant provider tests

Before instructing the user to spend money, confirm:

- one selected provider only;
- exactly one request per command;
- no retries;
- no fallback;
- no routing/model substitution;
- no multi-provider loop;
- only the selected provider's key is read;
- exact registered model/profile is used;
- canonical workload is unchanged;
- prompts/responses/API keys/raw error bodies are not printed or persisted;
- real attempts are stored as `prod`;
- workload hashes and request-profile identities are unchanged.

If any assumption is false, stop before a live request and fix it first.

---

## Pilot budget and call limits

Default:

- 1 initial live request per provider;
- at most 1–2 additional calls for that provider only when needed to validate a suspicious field or verify a fix;
- no provider exceeds 3 pilot calls without an explicit documented reason.

The goal is validation, not statistics.

Do not add loops, concurrency, scheduling, retries, batch execution, or an `all providers` command.

---

## Recommended provider order

1. OpenAI — known earlier live baseline;
2. Anthropic;
3. Google;
4. xAI.

Claude may change the order if credential/account access makes another order more practical, but document why.

---

## Exact paid command shape

Use:

```bash
python -m llm_metrics.real_benchmark --provider <provider> --real --workload interactive-chat-v1 --debug
```

Use the repository's existing virtual environment/interpreter conventions if needed.

Do not put an API key on the command line.

Before each call, Claude must tell the user:

- provider;
- exact model;
- request-profile id;
- workload;
- output cap;
- that exactly one paid API request will be made.

---

# Validate each live result

For every provider, inspect the pasted safe output and relevant saved request facts.

## 1. Request acceptance

Verify:

- correct provider/model/profile/workload;
- correct output cap;
- expected reasoning/thinking condition;
- expected cache policy;
- provider accepted the request.

Key/account/billing/model-access/setup failures are **not** provider reliability failures.

## 2. Streaming and TTFT

Confirm the stream produced actual generated text before completion and TTFT was triggered only by the first actual generated text, never metadata, role, thought/reasoning, heartbeat, empty, or usage-only events.

Do not persist or print the generated text merely for validation.

If the live event shape differs from fixtures, stop before the next provider and correct the adapter/test first.

## 3. Provider-authoritative usage

Confirm:

- `input_tokens`;
- `output_tokens`;
- `cached_input_tokens` when reported;
- absent/unknown remains `None`/NULL, never fabricated zero.

Different provider token counts for the same text are expected.

Provider-specific checks:

- Anthropic: whole-input accounting remains correct when cache read/create fields are present or absent.
- Google: live thought-token reporting remains consistent with output-token accounting and pricing assumptions.

## 4. Provider request id

Verify the documented source:

- OpenAI: `x-request-id`;
- Anthropic: `request-id`;
- Google: interaction id from the stream;
- xAI: response id from the stream.

If the live API does not expose one, store NULL honestly.

## 5. Completion/output-cap semantics

Confirm:

- requested max output and actual output stay separate;
- shorter responses are valid successes;
- hitting the cap is handled correctly;
- no continuation or retry occurs.

## 6. Cache facts

Do not infer cache behavior from latency.

Preserve:

- reported `0` = observed zero;
- absent = unknown/NULL;
- positive count = provider-reported cached input reuse.

Do not describe a request as `cold` unless the request semantics actually establish that.

## 7. Pricing and cost

Confirm stored rates match the current verified provider pricing and the cost calculation matches provider-authoritative usage.

If official pricing has materially changed, stop and correct `pricing.py`/provenance before continuing. Do not silently run with stale prices.

## 8. Persistence

Confirm the attempt records:

- environment `prod`;
- provider/model;
- workload id;
- request-profile id;
- origin cloud/region;
- cache policy;
- provider request id if known;
- requested output cap;
- input/output/cached token facts;
- effective rates and cost;
- outcome;
- successful TTFT, total latency, and throughput measurements.

Failed attempts must preserve established NULL/unknown semantics.

---

# Failure handling

## Setup/account failures

Examples:

- missing/invalid key;
- billing disabled/exhausted credits;
- permission/project problem;
- selected model unavailable;
- invalid account configuration.

These are not provider benchmark failures.

Explain the minimum account/setup action and wait for the user before retrying.

## Live protocol/integration mismatch

If live evidence shows the adapter fixture is wrong:

1. stop further paid calls;
2. preserve only sanitized, non-sensitive evidence;
3. compare against current official provider documentation;
4. make the smallest implementation correction;
5. add/update a regression test matching the observed shape;
6. run the full offline suite;
7. rerun only that provider once;
8. document the discrepancy and correction.

Do not weaken unknown-vs-zero, privacy, no-retry, or failure-classification semantics just to make the call pass.

---

# Code-change policy

Step 018 is primarily live validation.

Code changes are allowed only when live evidence demonstrates a real integration defect or verified provider change.

Any change must:

- be minimal;
- follow `CODING_GUIDELINES.md`;
- include a regression test;
- preserve workload hashes;
- preserve existing request-profile IDs unless request semantics materially change.

A change to model, endpoint, reasoning/thinking, cache control, or another material request setting is a methodology change. Do not silently edit an existing profile. Stop and explain the impact before versioning the profile.

Do not perform unrelated cleanup/refactoring.

---

# Evidence to record per provider

Maintain `prompts/018-output.md` with:

- date/time;
- provider;
- exact model;
- request-profile id;
- workload id;
- requested output cap;
- origin;
- outcome;
- llm-metrics request id;
- provider request id if known;
- input tokens;
- cached input tokens (`null` if unknown);
- output tokens;
- TTFT;
- total latency;
- output tokens/sec;
- total cost;
- effective input/output/cached rates;
- account/setup issues encountered;
- whether a code fix was required;
- any live API difference from Step 016 fixtures;
- number of paid calls and reason for any call beyond the first.

Never record prompts, responses, API keys, passwords, MFA codes, payment data, or raw provider error bodies.

---

# Completion criteria

Step 018 is complete when:

- all four providers have at least one understood live result, or a documented external blocker prevents validation;
- every successful provider has live-validated streaming, usage, request-id behavior where available, cost, and persistence;
- any integration mismatch has a regression test and is resolved or explicitly blocked;
- total calls per provider stay within the pilot limit unless documented;
- full offline tests pass after any code changes;
- `./run.sh` remains offline;
- `prompts/018-output.md` contains the complete pilot record.

At completion, do **not** begin Google Cloud deployment or scheduled benchmarking.

Stop and report:

- provider-by-provider live validation status;
- number of paid calls;
- total pilot API spend;
- any code changes and commit SHA;
- any unresolved provider/account blockers;
- whether the four-provider path is ready for a Google Cloud multi-day experiment.

---

## Marketing checkpoint

After the pilot, explicitly produce a short handoff for the Growth & Marketing workstream containing:

- milestone completed;
- providers live-validated;
- sample size;
- evidence available;
- limitations;
- whether anything is publishable now;
- suggested next growth/user-research action.

A valid conclusion is **do not publish performance comparisons yet** because the sample size is only validation-level.

---

## Focus

> **Help the user obtain the four API credentials safely, then validate one real request at a time before scaling anything.**
