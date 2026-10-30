# Claude Prompt — Step 001: Initial TTFT

We are starting a new open-source project called `llm-metrics`.

Long-term, this project will independently measure LLM provider performance such as TTFT, throughput, latency, reliability, and price.

DO NOT build the long-term system yet.

We will develop this project in extremely small, testable steps. I want each step to be easy to understand, review, test, and commit.

## Engineering rules

1. Primary language: Python.
2. Keep the architecture simple.
3. Do not add functionality that I did not request.
4. Every step must have automated tests.
5. We will have two environments: `test` and `prod`.
6. `test` must never call a real LLM provider unless explicitly requested in a future task.
7. Secrets must never be committed.
8. Prefer standard Python libraries unless an external dependency clearly helps.
9. Do not create a database, web UI, Docker setup, scheduler, cloud deployment, or real provider integration yet.
10. Do not implement future features speculatively.

## Progress tracking

Create `PROJECT_STATUS.md`.

This file is the persistent handoff document for future development sessions. It must contain:

- Project objective
- Current architecture
- Current environment setup
- What has been implemented
- What tests exist
- How to run the project
- Current limitations
- Decisions made
- Exact next recommended micro-step

Update `PROJECT_STATUS.md` at the end of every development step. A future coding agent should be able to read this file and understand exactly where the project currently stands.

Also create `DECISIONS.md`. Record important design decisions there and briefly explain why they were made.

## STEP 001 ONLY

Create the minimum Python project that can measure one metric: **Time To First Token (TTFT)**.

Do NOT integrate OpenAI, Anthropic, Google, OpenRouter, or any external LLM API yet.

Create a dummy LLM provider that simulates a streaming LLM response. It may receive a prompt, wait for a configurable amount of time, emit the first token, and optionally emit a few additional tokens.

Create a very small provider abstraction so that a real provider can replace the dummy provider later. Do not over-engineer it. Something conceptually equivalent to `LLMProvider.stream(prompt)` and `DummyProvider` is sufficient.

## TTFT

Measure elapsed wall-clock time between `request_started` and `first_token_received`. Use an appropriate monotonic high-resolution Python timer.

Return a simple result containing at least:

- provider
- model
- metric name
- TTFT in milliseconds

Example conceptual output:

```json
{
  "provider": "dummy",
  "model": "dummy-model-v1",
  "metric": "ttft",
  "value_ms": 100.4
}
```

Do not worry about the exact schema beyond keeping it simple and documented.

## Environments

Implement a minimal mechanism for `APP_ENV=test` and `APP_ENV=prod`.

For this step:

- `test` uses DummyProvider.
- `prod` should NOT yet call a real provider.
- If someone tries to execute an unsupported production provider, fail clearly and safely.

Do not add production credentials yet. Provide `.env.example` if useful, but never commit `.env`.

## Tests

Add focused automated tests. At minimum test:

1. DummyProvider emits tokens.
2. TTFT measurement produces a positive value.
3. Configured dummy delay is reflected approximately in TTFT.
4. Test environment uses DummyProvider.
5. Production environment does not accidentally call DummyProvider as if it were a real production provider.
6. Invalid environment configuration fails clearly.

Tests should run with one simple command.

## CLI

Provide one simple way to run the experiment locally, for example:

```bash
APP_ENV=test python -m llm_metrics
```

Expected human-readable output can be approximately:

```text
Provider: dummy
Model: dummy-model-v1
Metric: TTFT
TTFT: 100.4 ms
```

Keep this simple.

## README

Create a minimal README explaining what llm-metrics is, what Step 001 currently measures, what TTFT means, how to create the Python environment, how to run tests, and how to run the dummy measurement.

Clearly state that the current implementation uses a simulated provider and does not represent real LLM performance.

## Before finishing

Run all tests. Then inspect the repository for unnecessary complexity and remove anything that is not needed for Step 001. Update `PROJECT_STATUS.md`.

At the bottom of `PROJECT_STATUS.md`, write `### Next recommended micro-step` and recommend ONE small next step only. Do not implement that next step.

Finally give me:

1. Files created/changed.
2. Test command.
3. Test results.
4. Example execution command.
5. Example output.
6. Any design decision I should review.
7. The exact proposed Step 002, but DO NOT implement it.

Stop after Step 001.
