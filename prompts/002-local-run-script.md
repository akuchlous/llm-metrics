# Claude Prompt — Step 002: One-command local run

Read `PROJECT_STATUS.md`, `DECISIONS.md`, and `prompts/001-initial-ttft.md` before making changes.

Step 001 is complete. Preserve all existing behavior and tests.

## Goal

Make the current project easy to run from a Chromebook Linux terminal with **one command**:

```bash
./run.sh
```

This is a developer-experience step only. Do not add another metric or begin the dashboard yet.

## Requirements

1. Add an executable `run.sh` at the repository root.
2. It must work in a normal Chromebook Linux terminal with Python 3 available.
3. It should create `.venv` if it does not exist.
4. It should activate/use the virtual environment consistently.
5. It should run the automated tests before starting the current application/measurement.
6. It should run the existing application in `test` mode by default.
7. It must stop immediately if tests fail.
8. It should print short, understandable progress messages so the user knows what is happening.
9. Re-running `./run.sh` should be safe and should reuse the existing virtual environment rather than recreate it unnecessarily.
10. Preserve the existing direct invocation (`APP_ENV=test python -m llm_metrics`) if possible.

A successful run should feel approximately like:

```text
LLM Metrics — local test environment
✓ Python environment ready
✓ Tests passed
✓ Starting test measurement

Provider: dummy
Model: dummy-model-v1
Metric: TTFT
TTFT: ... ms
```

Exact wording is not important. Simplicity and reliability are.

## Environment behavior

`./run.sh` should default to `APP_ENV=test`.

Do not make `prod` functional in this step. The existing safety behavior where production cannot accidentally use the dummy provider must remain intact.

Do not add credentials or real providers.

## Tests

Add only the tests needed to give confidence in this step. Do not build an elaborate shell-testing framework.

At minimum verify that existing Python tests continue to pass. If practical and lightweight, add a test/check for the local-run behavior, but avoid unnecessary dependencies.

## Documentation

Update `README.md` so the primary Chromebook/Linux local workflow is:

```bash
git clone <repo>
cd llm-metrics
./run.sh
```

Keep the lower-level manual commands documented for debugging/development.

Update `PROJECT_STATUS.md` to reflect the actual repository state after Step 002.

The status file should now clearly include these sections (add them if absent):

- Current milestone
- Working right now
- Current user experience
- What I can see
- Current limitations
- Next recommended micro-step
- Do NOT implement yet

Under `Working right now`, use a small checklist showing completed capabilities.

Under `Current user experience`, document the exact local command.

## Important project rule

From this step onward:

**Never leave the repository in a state where `./run.sh` does not work. Every future step must preserve all previously working functionality.**

Record this as a project decision in `DECISIONS.md`.

## Prompt history

The `prompts/` directory is an immutable historical record of development instructions.

Do NOT modify existing prompt files. In particular, do not modify:

- `prompts/001-initial-ttft.md`
- `prompts/002-local-run-script.md`

Future prompts will be added as new numbered files.

## Scope guardrails — DO NOT implement these in Step 002

Do NOT add:

- SQLite or any database
- historical dummy data
- dashboard or web server
- Flask/FastAPI
- JavaScript/charting libraries
- total response time
- throughput
- p50/p95/p99
- real LLM providers
- scheduler
- Docker
- cloud deployment
- GitHub Actions unless strictly required (it should not be)

## Before finishing

1. Run the complete test suite.
2. Run `./run.sh` yourself and verify the end-to-end local experience.
3. Confirm that production safety behavior still works.
4. Update `PROJECT_STATUS.md`.
5. Update `DECISIONS.md` if needed.
6. Do not implement Step 003.

## Proposed direction after this step

The broader agreed direction is:

- Step 003: local persistence for metric observations (likely SQLite).
- Step 004: deterministic historical dummy TTFT data sufficient to exercise graphs.
- Step 005: first lightweight browser dashboard showing the TTFT story.

These are context only. **Do not implement them now.**

At completion, report:

1. Files changed.
2. Test command and result.
3. Exact `./run.sh` behavior.
4. Any portability assumptions for Chromebook/Linux.
5. Any design decision requiring review.
6. One proposed Step 003 only.

Stop after Step 002.
