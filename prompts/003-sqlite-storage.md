# Step 003 — Persist TTFT observations in SQLite

## Context

Read these files before making changes:

- `PROJECT_STATUS.md`
- `DECISIONS.md`
- `prompts/001-initial-ttft.md`
- `prompts/002-local-run-script.md`

Steps 001 and 002 are complete. The project currently measures TTFT using a dummy streaming provider and can be run locally with `./run.sh`.

This task adds only the smallest persistence layer needed for future historical metrics and dashboards.

## Engineering priorities

Treat this repository as if it will become public.

For implementation decisions, use this priority order:

**correctness → security → readability/maintainability → simplicity → minimal code**

Minimal line count is not the goal. Prefer clear, readable code over clever compression. A somewhat longer implementation is better when it is materially easier to understand, test, modify, or operate safely.

At the same time, avoid code bloat and premature architecture. Do not introduce abstractions, dependencies, configuration, helpers, classes, interfaces, or extensibility merely because they might be useful later. Implement what the current step needs. Good abstractions are appropriate when the current code already justifies them.

A useful rule for this project is:

> Write the smallest implementation that is easy to understand, test, modify, and operate safely.

## Objective

Persist each successful TTFT measurement to a local SQLite database.

After this step, running:

```bash
./run.sh
```

must still work as before, but the successful TTFT observation produced by the CLI must also be saved locally.

Do not build historical dummy data or a dashboard yet.

## Requirements

### 1. Use SQLite

Use Python's standard-library `sqlite3` module.

Do not add SQLAlchemy or another database dependency.

Use a local database file with a clear conventional location/name, for example:

```text
data/llm_metrics.db
```

Choose the exact location deliberately and document it.

The runtime database file must not be committed to Git. Add the appropriate ignore rule if needed.

### 2. Minimal observations table

Create one table for metric observations.

It must store at least:

- an automatically generated ID
- timestamp
- provider
- model
- metric name
- numeric metric value

For the current project, a stored row should conceptually represent:

```text
2026-10-30T...Z | dummy | dummy-model-v1 | ttft | 100.4
```

Use UTC timestamps.

Do not design a large future-proof schema. We need enough structure for upcoming historical graphs, not a general analytics platform.

### 3. Database initialization

The database/table should be initialized automatically when needed.

A fresh clone followed by:

```bash
./run.sh
```

must not require the user to manually create the database or run migrations.

Do not introduce a migration framework yet.

Initialization must be safe to run repeatedly.

### 4. Persist successful TTFT measurements

After the existing TTFT measurement succeeds, save that observation.

Preserve the existing human-readable CLI output.

Add a small confirmation that makes persistence visible to the developer, for example:

```text
Saved observation to data/llm_metrics.db
```

The exact wording may differ if there is a good reason.

Do not persist failed/incomplete measurements.

### 5. Keep storage separate from measurement

TTFT measurement logic should not directly contain SQLite implementation details.

Create a small storage module/function rather than embedding SQL into `ttft.py`.

Keep the abstraction minimal. Do not introduce repositories, ORMs, dependency injection frameworks, service layers, or other architecture that Step 003 does not need.

### 6. Test environment

`APP_ENV=test` continues to use the DummyProvider.

The local SQLite observations created while running test mode are simulated measurements and must not be confused with future production measurements.

If necessary, include an `environment` field in the observation schema so that `test` and future `prod` observations can be distinguished. Prefer doing this now if it remains simple, because the dashboard must later label simulated data clearly.

Document the choice in `DECISIONS.md`.

### 7. Tests

Add focused automated tests covering at least:

1. A fresh database initializes successfully.
2. Initialization is idempotent.
3. A TTFT observation can be inserted.
4. Stored provider/model/metric/value are correct.
5. Timestamp is stored.
6. Environment is stored if the schema includes it.
7. Multiple observations can be stored without overwriting earlier observations.
8. Existing Step 001 and Step 002 tests continue to pass.
9. `./run.sh` still completes successfully and results in a stored TTFT observation.

Tests must use temporary databases/directories. They must not write test data into the developer's normal local database.

Tests should verify meaningful externally observable behavior rather than implementation details. Do not create a large test framework for this small persistence layer.

### 8. Preserve one-command local development

This is a hard requirement:

```bash
./run.sh
```

must remain the normal Chromebook/Linux developer entry point.

Do not require Docker.
Do not require an external database.
Do not require manual setup beyond what `run.sh` already performs.

### 9. Public-repository security

Before committing, inspect the repository as if it were already public.

- Do not commit credentials, API keys, tokens, `.env` files, runtime SQLite databases, virtual environments, caches, or machine-specific/private artifacts.
- Ensure the runtime database path is ignored by Git.
- Use parameterized SQL for dynamic values; do not construct SQL by concatenating measurement values.
- Test databases must be isolated from the developer's normal database.
- Avoid logging or persisting information that is not required for the metric observation.
- Do not weaken the existing safe `prod` behavior.

### 10. Documentation

Update:

- `README.md`
- `PROJECT_STATUS.md`
- `DECISIONS.md`

`PROJECT_STATUS.md` must accurately describe:

- current architecture
- SQLite location
- observations schema
- how initialization works
- how a TTFT measurement gets persisted
- tests and test count
- current limitations
- exact next recommended micro-step

The next recommended micro-step should be **Step 004: deterministic historical simulated TTFT data** so that we have enough old data for graphs.

Do not implement Step 004.

## Explicitly out of scope

Do NOT implement any of the following in Step 003:

- historical dummy-data generation
- dashboard or web server
- Flask/FastAPI
- charts
- p50/p95/p99
- total response time
- throughput
- availability/error metrics
- real LLM providers
- OpenAI/Anthropic/Gemini/OpenRouter integration
- scheduler/cron
- cloud deployment
- Docker
- PostgreSQL
- SQLAlchemy/ORM
- migrations framework
- REST API

## Engineering rule

Never leave the repository in a state where `./run.sh` does not work.

Every step must preserve all previously working behavior unless the prompt explicitly changes it.

Do not write code today solely for a feature scheduled for a later step.

## Before finishing

1. Run the full test suite.
2. Run `./run.sh` from a clean-enough local state and verify database initialization and persistence.
3. Perform a public-repository/security review.
4. Perform a code-quality/bloat review:
   - Can any new file or abstraction be eliminated without hurting readability or maintainability?
   - Is any code present only because it might be useful later?
   - Are tests focused on meaningful behavior rather than implementation details?
   - Did we add any dependency that the Python standard library can reasonably replace?
   - Is there duplicate logic?
   - Is the resulting code easy for another engineer to read and modify?
5. Remove unnecessary complexity, but do not sacrifice readability or maintainability merely to reduce line count.
6. Update `PROJECT_STATUS.md`.
7. Update `DECISIONS.md` for durable storage/schema decisions.
8. Do not modify historical prompt files under `prompts/` other than this prompt update made before implementation begins.

## Final response

Report:

1. Files created/changed.
2. Database location and schema.
3. Test command and result.
4. Example `./run.sh` execution/output.
5. How you verified that the observation was actually persisted.
6. Security/public-repository checks performed.
7. Readability/maintainability and code-bloat review performed.
8. Any design decision or concern that should be reviewed.
9. Exact proposed Step 004, but DO NOT implement it.

Stop after Step 003.
