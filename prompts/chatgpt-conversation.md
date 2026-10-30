# ChatGPT conversation / decision log

This is a concise chronological record of the ChatGPT discussions that shaped `llm-metrics` and the broader `llmxchange` direction. It is not a verbatim transcript. Keep it current as meaningful project decisions are made.

_Last updated: 2026-10-30 05:59 IST_

## 2026-10-25 — Provider/API landscape

- Discussed connecting llmxchange to major LLM APIs including OpenAI, Anthropic/Claude, Google/Gemini, and inference providers such as Together, Groq and Fireworks.
- Direction: provider integrations should eventually sit behind a common abstraction rather than being hard-coded into routing logic.

## 2026-10-25 — Sync versus async inference

- Discussed supporting both synchronous and asynchronous requests.
- Key distinction decided: scheduling and result delivery should be independent concepts.
- `max_queue_time = 0` means execute/route immediately with no waiting for a cheaper opportunity.
- A non-zero queue/deadline can allow time-flexible work to wait for cheaper/idle capacity.
- Delivery can independently be streaming, synchronous, or asynchronous/polling/webhook.

## 2026-10-25 — Idle capacity / exchange thesis

- Identified idle GPU capacity as a possible core exchange opportunity: providers may discount unused capacity during low-utilization periods.
- Long-term concept: buyers provide price/deadline/quality constraints while sellers expose capacity/asks; llmxchange matches them.
- Potential execution classes: realtime, deadline-based, and batch/spot.

## 2026-10-25 — Economics and fraud

- Did rough infrastructure/take-rate reasoning; routing infrastructure should be much cheaper than the underlying inference at meaningful scale, though networking, observability, retries, billing and support matter.
- Discussed starting with a transparent exchange fee (roughly 10% as an initial hypothesis) while leaving room for spread/market pricing later.
- Prepaid credits were preferred for an MVP.
- Fraud risks discussed: stolen payment methods, stolen API keys, malicious provider metering, buyer/provider collusion and promotional abuse.
- For an early system using established upstream providers, sophisticated seller fraud controls are not an MVP requirement.

## 2026-10-26 — OpenRouter comparison

- Observed that OpenRouter already provides much of the gateway/routing functionality originally considered: many models/providers, performance-aware routing, pricing controls, fallback, credits and batch capabilities.
- Decision: do not begin by building another general OpenRouter-style proxy.
- Stronger path: start with independent measurements/data, then quality evaluation, routing, and finally an exchange/marketplace.

## 2026-10-26 — Four independent projects

Agreed to structure the broader effort as independently useful projects that can later be combined:

1. **LLM Metrics** — measure provider/model performance such as TTFT, throughput, latency, availability/errors and price.
2. **LLM Quality Bench** — maintain test data and scoring to measure output quality.
3. **LLM Router** — route requests using measured performance, quality, price and constraints.
4. **LLM Exchange** — bids/asks, capacity, deadlines, async jobs and eventual settlement/market mechanics.

A small shared schema/spec may eventually connect them, but avoid a large shared framework early.

## 2026-10-26 — Public/open development strategy

- Plan: publish incremental experiments/results frequently on LinkedIn.
- Use the public GitHub work to attract users, feedback and contributors rather than waiting for a finished product.
- Claude is used primarily for small implementation steps; ChatGPT/OpenAI reviews repository state, architecture, measurement methodology and determines the next micro-step.
- GitHub is the source of truth rather than relying on conversational memory.

## 2026-10-30 — `llm-metrics` Step 001

- Decided to begin extremely small: one dummy provider, one dummy model, one metric (TTFT), test/prod environment separation, Python-first implementation and automated tests.
- Real providers, databases, dashboards, schedulers and deployment were intentionally excluded from Step 001.
- Claude implemented Step 001; `PROJECT_STATUS.md` reports the dummy streaming provider, TTFT measurement, CLI, environment safety and 16 tests.

## 2026-10-30 — Local development and dashboard direction

Additional requirements were established:

- Must run easily in the Chromebook Linux terminal.
- Normal local startup should eventually be a single command: `./run.sh`.
- Test environment should contain enough historical simulated data to make graphs useful from early development.
- A lightweight dashboard should appear early rather than being bolted on after many backend steps.
- Dashboard should tell a coherent story, initially: **How is this provider/model performing, and is performance changing?**
- Simulated/test data must be clearly labeled as simulated.
- Every micro-step should leave a working, usable repository; never intentionally break previously working behavior.

Incremental direction:

- Step 001: dummy provider + TTFT — complete.
- Step 002: one-command Chromebook/Linux local run (`./run.sh`) — complete.
- Step 003: local metric persistence with SQLite — next.
- Step 004: deterministic historical dummy TTFT observations for graphs.
- Step 005: first lightweight browser dashboard for TTFT.
- Later: percentiles/time ranges, total latency, throughput, availability/errors, price, then first real provider/model.

## 2026-10-30 — Prompt history as repository artifact

- Decision: store the exact implementation prompts given to Claude under `prompts/`.
- Number prompts sequentially (`001-...`, `002-...`, etc.).
- Used prompt files are immutable historical records; new decisions belong in new prompts rather than rewriting history.
- `PROJECT_STATUS.md` remains the current implementation source of truth.
- `DECISIONS.md` records durable engineering decisions.
- This file records the higher-level ChatGPT discussion and product/project decisions in concise chronological form.

## 2026-10-30 05:56 IST — Step 002 completed and reviewed

- Claude committed Step 002 as commit `dd6d19b`: one-command local run with `./run.sh`.
- `run.sh` creates or reuses `.venv`, runs the full test suite, stops on test failure, then runs the TTFT measurement; `APP_ENV` defaults to `test`.
- Claude added tests for the run script and updated README, `PROJECT_STATUS.md`, and `DECISIONS.md`.
- Review decision: Step 002 stayed within scope and did not jump ahead into persistence, dashboard, or real providers.
- Next decision: Step 003 should add only SQLite persistence for individual TTFT observations while preserving `./run.sh` as the one-command developer experience.

## 2026-10-30 05:59 IST — Step 003 prompt created

- Added `prompts/003-sqlite-storage.md`.
- Step 003 uses Python standard-library `sqlite3`; no ORM, external database, migrations framework, dashboard, or real provider.
- Each successful TTFT observation will be persisted with timestamp, provider, model, metric, value, and preferably environment so simulated test data can later be distinguished from production data.
- Database initialization must be automatic and idempotent so a fresh clone plus `./run.sh` remains sufficient.
- Tests must use temporary databases and must not pollute the developer's local metrics database.
- Planned Step 004 remains deterministic historical simulated TTFT data to provide enough observations for meaningful graphs.

## Current state

As of 2026-10-30 05:59 IST:

- Step 001 — complete.
- Step 002 — complete and reviewed.
- `prompts/001-initial-ttft.md` — historical Step 001 prompt.
- `prompts/002-local-run-script.md` — historical Step 002 prompt.
- `prompts/003-sqlite-storage.md` — current implementation prompt.
- Next action: point Claude at `prompts/003-sqlite-storage.md`, have it implement only Step 003, then have ChatGPT review the repository before creating Step 004.
