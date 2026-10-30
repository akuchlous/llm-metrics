# Project direction log

Concise context not captured by `PROJECT_STATUS.md` or `DECISIONS.md`. Keep only decisions that affect future work.

_Last updated: 2026-10-30_

## Product direction

`llmxchange` is planned as four independently useful projects:
1. **LLM Metrics** — independent provider/model performance measurements.
2. **LLM Quality Bench** — standardized quality tests and scoring.
3. **LLM Router** — route using performance, quality, price, and constraints.
4. **LLM Exchange** — later add bids/asks, capacity, deadlines, and async jobs.

Do not start by rebuilding an OpenRouter-style gateway. Build useful measurement data first, then quality, routing, and exchange mechanics.

## Development workflow

- GitHub is the source of truth.
- Claude implements one small numbered step.
- ChatGPT reviews the actual code before the next step is created.
- Material issues get a corrective step before new functionality.
- Code, docs, and prompts follow the engineering principles in `DECISIONS.md`.
- Used prompts remain immutable history.

## Local product direction

The local developer experience should remain one command: `./run.sh`.

Planned progression:
- Step 001 — dummy provider + TTFT: complete.
- Step 002 — one-command local run: complete.
- Step 003 — SQLite persistence: complete and reviewed.
- Step 004 — deterministic simulated TTFT history.
- Step 005 — first lightweight TTFT dashboard.
- Later — percentiles/time ranges, more metrics, then real providers.

The first dashboard should answer: **How is this provider/model performing, and is performance changing?** Simulated data must always be clearly labeled.

## Step 003 review — 2026-10-30

Commit `7c58e1a` adds a small `sqlite3` storage module, automatic/idempotent initialization, parameterized inserts, UTC timestamps, environment separation, temporary DBs in tests, and git-ignored runtime data.

Review result: **pass; no corrective code step required.** The implementation is small and readable, keeps storage out of TTFT measurement code, preserves the safe `prod` guard, and stays within Step 003 scope.

Known issues are non-blocking: storage errors currently surface as a traceback; `value_ms` is intentionally metric-specific; and Step 004 will need a deliberate way to insert historical timestamps without over-generalizing storage.

Next action: create Step 004 only after this review gate.
