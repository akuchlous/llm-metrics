# Step 018d — Real PostgreSQL integration proof and safe migration gate

**Status:** Pending. Implement **only 018d** and stop for ChatGPT review. No paid GCP or LLM operations.

## Why this step

Read `prompts/018c-output.md` and actual implementation. Step 018c reports 359 passing offline tests, dialect-aware `LLM_METRICS_DATABASE_URL`, PostgreSQL compilation tests, and all four role-specific design questions. **It did not execute SQL against a live PostgreSQL server.** Before Cloud SQL provisioning or Cloud Run deployment, prove actual PostgreSQL behavior on a disposable local database.

Two concrete issues discovered in review:
- `storage._ensure_schema()` silently runs `alembic stamp head` on **PostgreSQL with pre-existing tables but no Alembic revision**, assuming a correct schema that was never validated. An unknown/partial schema must fail closed instead.
- Migration configuration currently passes a URL (possibly with a password) to Alembic. Verify errors, configuration interpolation (especially `%` in encoded passwords), debug output and logs cannot expose credentials.

The older 018a plan referred to first cloud deployment as 018c; 018c actually became a dialect-correctness code step. **018d is the final no-cloud PostgreSQL integration gate; a later reviewed micro-step will provision Cloud SQL** in the existing GCP project `llm-metrics-513617`. This is not authorization to create billable resources.

## Mandatory reading

Read `chatgpt-guidelines.md`, `prompts/PROMPT_WRITING_CONTRACT.md`, `prompts/DESIGN_QUESTIONS.md`, `CODING_GUIDELINES.md`, `PROJECT_STATUS.md`, `DECISIONS.md`, `prompts/chatgpt-conversation.md`, `prompts/018c-postgresql-storage-readiness.md`, `prompts/018c-output.md`, `llm_metrics/config.py`, `llm_metrics/storage.py`, `migrations/env.py`, baseline Alembic revision, actual related tests and `design-questions/018c/`. Follow repository conventions; inspect actual code, do not rely on reports alone.

## Single objective

**Demonstrate the current v7 schema and persistence contract on a real, disposable PostgreSQL instance, and close only the database initialization/security defects needed to make that test trustworthy.** No new feature or production platform.

## Implementation tasks (bounded)

1. **Disposable local integration harness.** Prefer an existing local PostgreSQL installation or a deliberately invoked, short-lived PostgreSQL Docker container; do not install or operate a persistent service automatically. Add focused integration tests runnable on explicit opt-in with a dedicated `TEST_POSTGRES_URL` (or similarly named variable). Fail/refuse if URL is absent or looks like a production/cloud host; never touch an existing shared database. Ensure tests use their own disposable database/schema, do not erase arbitrary data, and clean up resources. Normal `./run.sh` and unit tests must remain offline and independent of Docker/Postgres.
2. **Real PostgreSQL tests.** Against the disposable server verify: Alembic baseline creates v7 tables/indexes/FK and revision; one successful request with observations round-trips; one failed request retains unknown token/cost and no latency observations; CHECK/FK rejection; atomic rollback on bad observation; environment isolation; cache-policy filtering; spend aggregation; `ON CONFLICT DO NOTHING` observation seeding twice without duplicates; restart/reconnect and data durability; and readable timestamps/ordering. Use canonical synthetic test requests, **no provider API calls**.
3. **Fail-closed schema lifecycle.** PostgreSQL with **no application tables** may run Alembic baseline; with a known Alembic revision may upgrade. PostgreSQL with application tables but **no revision** must raise a sanitized, actionable error, not silently `stamp head`. Do not assume compatibility or auto-repair partial schemas. Keep the existing SQLite v0→v7 legacy bridge untouched. Do not run concurrent destructive migrations, auto-provision cloud databases, or add new schema fields.
4. **Safe credentials and migration configuration.** Prove Alembic/SQLAlchemy failure paths redact passwords, including special characters/percent-encoded URL values. Prefer handing Alembic a SQLAlchemy Connection via `config.attributes["connection"]` or an equivalently safe minimal approach rather than interpolating a raw credential-bearing URL into config. Avoid printing, storing, or logging database credentials or test URL. If a connection fails, return a sanitized error with no secret. Add focused regression tests.
5. **Keep footprint small.** Fix only failures uncovered by integration tests and the two issues above. Preserve SQLAlchemy Core, v7 semantics, all old SQLite tests, existing API/HTML/provider behavior, and exact model/profile/workload metrics. If a genuinely broad redesign is required, stop and document it rather than expanding 018d.

## Verification and evidence

- Report explicit test command(s), PostgreSQL major version actually used, connection method (local/Docker), and results for each integration case. **SQL compilation alone does not satisfy this step.** If no safe disposable server is available, provide the harness and report the step **blocked/unverified**, not complete; do not claim PostgreSQL integration tested.
- Run full offline suite and `./run.sh` unchanged; run coding/style checks under `CODING_GUIDELINES.md`. No paid LLM calls, no cloud resources, no automatic scheduler.
- No prompts, generated responses, raw provider errors, passwords, credentials or secret URLs in test output, source, commit history, debug prints or docs. Preserve NULL-vs-zero, request identity, effective price basis, atomicity and population boundaries.

## Required learning and output

Follow `prompts/DESIGN_QUESTIONS.md` and add all four **Step 018d** files:
- `design-questions/018d/lead-engineer.md`
- `design-questions/018d/principal-engineer.md`
- `design-questions/018d/senior-manager.md`
- `design-questions/018d/director.md`

Each: one-line grounded context, distinct role-appropriate question, answer from actual work and good/weak/improve critique. Update `design-questions/README.md`.

Write `prompts/018d-output.md`: changed files, PostgreSQL test matrix and actual server evidence, migration safety decision, secrets/redaction evidence, SQLite regression results, complete test counts, `./run.sh`, style checks, risks, no GCP/API spend confirmation, concise Design Q&A, **MARKETING CHECKPOINT** (likely 'not publishable yet'), commit SHA if available, and **exactly one** next recommended micro-step.

Update `PROJECT_STATUS.md` and `DECISIONS.md` as needed. **Append only** to `prompts/chatgpt-conversation.md`; preserve every earlier entry including the older 018a roadmap and 018c conclusions.

## Exclusions and stop condition

**Do not** provision Cloud SQL, create or change resources in `llm-metrics-513617`, add Cloud Run/containers/Secret Manager/Scheduler, deploy a service, run paid OpenAI calls, introduce dashboard population changes, expand to other providers, or auto-run any benchmark.

When all artifacts are committed, **STOP**. ChatGPT will review the actual code/tests and authorize the next narrowly scoped cloud step. If the integration harness cannot execute locally, stop with explicit blocker and evidence instead of starting cloud provisioning.

> Goal: one real PostgreSQL-backed storage proof, with no silent schema trust and no secret leakage.
