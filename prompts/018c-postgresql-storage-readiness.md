# Step 018c — PostgreSQL-ready storage connection and dialect correctness

## Status
Pending implementation. Execute this micro-step only; stop for ChatGPT review.

## Context and objective
Step 018b introduced SQLAlchemy Core and Alembic while retaining local SQLite behavior (see `prompts/018b-output.md`). Its report says storage is portable, but the current code still hardcodes `sqlite:///` in `storage.connect()`, uses SQLite `PRAGMA` in `_ensure_schema()`, and calls `sqlalchemy.dialects.sqlite.insert` for duplicate-safe observation seeding. The SQLAlchemy table metadata also omits the observation-to-request foreign key that the Alembic baseline defines.

**One objective:** make the existing storage layer genuinely capable of using a PostgreSQL URL and executing its existing reads/writes/migrations without SQLite-only assumptions, while keeping the default local SQLite path and historical migrations intact.

No GCP provisioning, deployment, running scheduler, or provider calls. This is a small, independently reviewable prerequisite for deploying Cloud SQL later. The previous 018a roadmap bundled Cloud SQL and Cloud Run as 018c; split further because the newly inspected 018b code demonstrates a database compatibility gap.

## Read before changes
- `CODING_GUIDELINES.md`, `DECISIONS.md`, `PROJECT_STATUS.md`
- `prompts/018a-output.md`, `prompts/018b-output.md`
- `prompts/chatgpt-conversation.md` (append only)
- `llm_metrics/storage.py`, `llm_metrics/config.py`
- `migrations/env.py`, `migrations/versions/f1a2b3c4d5e6_baseline_v7_schema.py`
- all storage tests and callers of `storage.connect`, `config.get_db_path`, and `save_new_observations`
- `requirements.txt` and the hash-pinning installation rules

Before coding, explain briefly how you will address the SQLite-specific code without rewriting analytics or providers. State whether local PostgreSQL integration testing is actually available; do not claim testing against PostgreSQL if only dialect compilation was tested.

## Scope / requirements

1. **Explicit, safe database choice.** Keep the present `LLM_METRICS_DB_PATH` default/override and SQLite path API working. Add one small, explicit PostgreSQL database URL configuration mechanism (for example `LLM_METRICS_DATABASE_URL`) with documented precedence; avoid a broad config/DI redesign. Parse/validate supported schemes, fail closed on invalid/conflicting configuration, and never print or log URL credentials. Tests must not consult live environment variables.
2. **Connection/engine support.** SQLAlchemy Core should construct SQLite engines for local paths and PostgreSQL engines for explicit PostgreSQL URLs, with minimal call-site churn. Use one reputable, maintained PostgreSQL driver, pin exact packages and hashes consistently with repo policy. Avoid an unbounded engine cache for arbitrary secret-bearing URL strings; do not accidentally expose credentials through errors or reprs. Preserve transaction atomicity and existing return shapes.
3. **Dialect-aware schema lifecycle.** For PostgreSQL, use Alembic for fresh database initialization and forward migration; never run SQLite `PRAGMA` or the v0–v7 SQLite-only bridge there. For SQLite, preserve existing v0–v7 legacy upgrades and Alembic stamping without loss. Do not run schema DDL/migrations for every request/connection. Document how future production migrations will be managed safely (especially separate migration-before-traffic versus concurrent startup); do not build cloud deployment in this step.
4. **Portable insert/query semantics.** Fix SQLite-specific `on_conflict_do_nothing` usage with a narrow dialect-aware solution (SQLite and PostgreSQL) or a simple safe portable alternative preserving idempotency. Verify and correct other dialect-specific SQL as needed. Preserve observed result ordering, timestamp format, exact-null-vs-zero, and pricing facts.
5. **Schema fidelity.** Reconcile SQLAlchemy table metadata with the Alembic baseline (particularly the `observations.request_id -> requests.id` foreign key), maintaining SQLite legacy compatibility. Preserve v7 columns, constraints, indexes, failure semantics, and no guessed historical facts. Do not silently create a new product schema version. If a mismatch requires a migration, explain before editing the historical baseline and choose the safest minimal approach.
6. **Test evidence.** Full offline suite and `./run.sh` must pass without PostgreSQL running. Add targeted regression tests for URL selection/redaction, dialect-aware behavior, schema parity/foreign key, and PostgreSQL DDL/SQL compilation. If an existing local disposable PostgreSQL service is available without cloud provisioning, execute optional integration tests for creating the baseline schema, one success + one failed attempt, atomic writes, real/test isolation, idempotent seed and read/aggregate behavior. If unavailable, say **PostgreSQL integration not yet verified**, not 'fully tested.' Do not make network provider calls.
7. **Privacy/security.** No prompts, responses, keys, raw provider errors, or DB credentials in logs; do not weaken strict database CHECKs to make tests pass.

## Strictly out of scope
- No Cloud SQL instance, billing setup, GCP project/resource, Dockerfile, Cloud Run Job/Service, Secret Manager, Cloud Scheduler, scheduling/cadence/cost guardrails, Gunicorn, public deployment.
- No changes to providers, model/request profiles, workload text/hashes, real benchmark behavior, analytics/API/dashboard UI, or new product features.
- No ORM, generic repository framework, extensive code cleanup, data migrations from local SQLite to cloud, or paid API calls.
- No reliance on an externally provisioned PostgreSQL instance to pass the normal test suite.

## Finish and stop
- Run all tests, offline `./run.sh`, and repository style/quality checks.
- Create `prompts/018c-output.md` with changed files, architecture/configuration behavior, Postgres driver/dependency versions, the SQLite-vs-PostgreSQL test matrix (mark actual integration vs compile-only), preserved invariants, limits, commit SHA and **one** smallest recommended next step.
- Update `PROJECT_STATUS.md` / `DECISIONS.md` only as necessary for current truth.
- **Append** an 018c evolution entry to `prompts/chatgpt-conversation.md` with no edits to any preexisting text; the older 018a suggested roadmap remains as historical thinking.
- Commit this step; stop for ChatGPT review. Do not begin any cloud work without a separately reviewed next prompt.

## Success
Local SQLite behavior stays unchanged, PostgreSQL is explicitly selectable without exposing credentials, storage and schema/SQL paths are dialect-correct with honest test evidence, and no production infrastructure has been created.

> Focus: correct the connection-and-dialect seam before paying for Cloud SQL.
