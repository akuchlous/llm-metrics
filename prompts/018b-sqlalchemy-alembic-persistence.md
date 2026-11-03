# Step 018b — SQLAlchemy Core + Alembic persistence portability

## Status

Pending implementation.

## Context

Step 018a established that the OpenAI benchmark path itself already works, but the current persistence layer is SQLite-specific and therefore not ready for the planned durable Google Cloud runtime.

Read `prompts/018a-output.md` before making changes.

This step intentionally addresses **one responsibility only**: make the existing persistence layer portable to PostgreSQL while preserving current behavior and local SQLite development.

Do not provision Google Cloud resources in this step.

---

## Objective

Migrate the existing persistence implementation from direct `sqlite3` SQL to **SQLAlchemy Core** and introduce **Alembic** as the schema migration mechanism, while preserving the current schema, semantics, public storage behavior, local SQLite workflow, and all benchmark facts.

At the end of 018b:

- local development/tests still work with SQLite;
- the same SQLAlchemy Core schema is capable of targeting PostgreSQL later;
- Alembic owns schema creation/evolution going forward;
- existing storage semantics remain unchanged;
- no cloud resource has been created;
- no provider API call has been made.

This is a portability/refactoring step, not a feature step.

---

## Required reading

Before changing code, read at least:

- `CODING_GUIDELINES.md`
- `DECISIONS.md`
- `PROJECT_STATUS.md`
- `prompts/chatgpt-conversation.md`
- `prompts/017-output.md`
- `prompts/018a-output.md`
- `llm_metrics/storage.py`
- `llm_metrics/config.py`
- `llm_metrics/benchmark.py`
- `llm_metrics/analytics.py`
- `llm_metrics/query.py`
- `tests/test_storage.py`
- any tests that directly depend on SQLite-specific behavior
- `requirements.txt`
- `scripts/install_requirements.py`

Before implementation, briefly report:

1. the current public storage functions/call patterns that other modules rely on;
2. which SQLite-specific behaviors must be preserved or deliberately retired;
3. the exact files expected to change;
4. any compatibility risk you see before coding.

Then implement only this step.

---

## Core requirements

### 1. Use SQLAlchemy Core, not ORM

Use SQLAlchemy Core tables/statements/transactions.

Do **not** introduce:

- declarative ORM models;
- sessions;
- lazy loading;
- identity maps;
- repository/service abstractions that are not needed;
- a generic database framework beyond what the current product requires.

Keep the persistence code explicit and easy to audit.

The current storage module is intentionally close to SQL. Preserve that character.

---

### 2. Preserve the current schema and meaning

The current schema version is v7. Do not add product fields or reinterpret existing data.

Preserve the existing tables and facts:

- `requests`
- `observations`

Preserve column names, meanings, NULL semantics, CHECK constraints, indexes, foreign-key intent, and request/observation relationships as closely as supported across SQLite and PostgreSQL.

Especially preserve:

- `environment` separation (`test` vs `prod`);
- success/failure fact consistency;
- failed attempts having unknown token/cost facts rather than fabricated zeroes;
- `provider_request_id` nullable when absent;
- historical `workload_id` / origin / request profile remaining unknown when not recorded;
- `cached_input_tokens = 0` meaning provider-reported zero and NULL meaning unknown/not reported;
- effective input/output/cached prices stored per request;
- requested max output tokens remaining separate from actual output tokens;
- request + observations written atomically;
- observations for failed attempts remaining absent;
- existing uniqueness/index semantics.

Do not weaken constraints merely because one database engine expresses them differently.

If an exact cross-engine constraint is not portable, document the difference and preserve the invariant in the narrowest reliable layer.

---

### 3. Alembic becomes the forward migration mechanism

Introduce Alembic with a first baseline representing the current v7 schema.

The baseline must describe the current schema; it must not invent a new v8 product schema merely because the implementation mechanism changes.

Going forward, schema evolution should use Alembic revisions rather than adding more application-owned `PRAGMA user_version` upgrade branches.

However, existing local SQLite databases may contain valuable development/history data created by schema versions 0–7. Do not silently destroy that compatibility.

Choose and document a simple transition strategy that preserves existing local data. Acceptable approaches include retaining the old v0→v7 SQLite upgrade path only as a legacy bridge before Alembic takes ownership, if that is the smallest reliable solution.

Do not guess historical facts during migration.

---

### 4. Keep local SQLite working

Local development must remain simple.

The current developer workflow uses a local SQLite file under `data/` and tests use temporary SQLite databases. Preserve that workflow unless a very small compatibility adapter is needed.

Avoid forcing developers to install or run PostgreSQL for normal local development or the offline test suite.

Do not require Google Cloud credentials or provider API keys.

If the storage configuration needs to evolve from a filesystem path toward a database URL, keep backward compatibility with the current local configuration where practical. Do not cause a repository-wide configuration rewrite in this step unless genuinely necessary.

---

### 5. Preserve storage-facing behavior for callers

Do not use this migration as an excuse to redesign analytics, benchmark orchestration, dashboard, or API code.

Prefer preserving the existing storage function responsibilities and return shapes so callers require minimal or no changes.

If a function signature must change to support SQLAlchemy engines/URLs, make the smallest change possible and update all call sites/tests consistently.

Do not introduce a broad dependency-injection framework.

---

### 6. Dependencies must follow repository policy

The repository installs with `pip --require-hashes`.

Add only the dependencies actually required for this step, expected to include SQLAlchemy and Alembic plus unavoidable transitive/runtime dependencies.

Follow the repository's existing dependency policy:

- pinned versions;
- hashes present;
- no unnecessary packages;
- versions chosen consistently with the standing project guidance.

Do not add PostgreSQL drivers yet unless they are strictly required to complete and test this code-only portability step. PostgreSQL connectivity itself belongs to the later cloud/database micro-step.

---

## Testing requirements

All tests remain offline.

At minimum verify:

1. a fresh SQLite database can be created from the new migration/schema mechanism;
2. all current request/observation write semantics remain atomic;
3. all current query/read behavior remains equivalent;
4. CHECK/validation behavior remains equivalent, including unknown-vs-zero semantics;
5. real and simulated populations remain separate;
6. cache-policy filtering remains correct;
7. price basis remains historically preserved;
8. failed attempts never enter successful metric populations;
9. hostile/string values remain bound parameters rather than executable SQL;
10. existing local SQLite v7 data can transition without losing rows or changing unknown facts;
11. the schema/migration head is deterministic and testable;
12. `./run.sh` remains offline and works;
13. the complete existing test suite passes.

Do not weaken tests simply because exception classes change from `sqlite3.IntegrityError` to a SQLAlchemy-wrapped integrity exception. Update tests to assert the appropriate portable contract without losing the underlying invariant.

If practical without requiring a PostgreSQL service, add focused tests that compile or inspect the schema for the PostgreSQL dialect so obvious SQLite-only constructs are caught before the cloud step. Do not create a complex fake PostgreSQL environment.

---

## Explicitly out of scope

Do **not** do any of the following in 018b:

- create Cloud SQL;
- create any GCP project/resource;
- create a Cloud Run Job or Service;
- add Docker deployment configuration;
- add Secret Manager integration;
- add Cloud Scheduler;
- add run-count or budget scheduling logic;
- change OpenAI or any other provider code;
- change provider/model/request-profile semantics;
- change workloads or workload hashes;
- add Anthropic/Google/xAI/DeepSeek onboarding;
- change dashboard/API population selection;
- add Gunicorn;
- make a paid or network provider call;
- perform unrelated cleanup.

If implementation exposes a reason one of these is required, stop and report rather than expanding scope.

---

## Documentation and decision record

Update documentation only where needed to accurately record the persistence transition.

In particular:

- update `DECISIONS.md` to record adoption of SQLAlchemy Core + Alembic and the rationale;
- update `PROJECT_STATUS.md` with the completed 018b state;
- append the evolution to `prompts/chatgpt-conversation.md` without deleting or rewriting older thinking;
- create `prompts/018b-output.md`.

`prompts/chatgpt-conversation.md` is an append-only record of how the product thinking evolved. Never remove an older direction merely because a later decision superseded it.

---

## `prompts/018b-output.md` must include

- summary of what changed;
- files changed;
- dependency changes;
- old persistence architecture vs new persistence architecture;
- how SQLite local development remains supported;
- how existing v7 local databases transition safely;
- Alembic revision/head information;
- constraints/invariants preserved;
- any unavoidable SQLite/PostgreSQL differences;
- test counts/results;
- `./run.sh` result;
- confirmation that no cloud resources and no paid/provider calls were used;
- commit SHA;
- exactly one recommended next micro-step.

Do not automatically start the next micro-step.

---

## Completion criteria

018b is complete only when:

- persistence uses SQLAlchemy Core rather than direct application `sqlite3` statements for the forward storage implementation;
- Alembic owns the forward schema definition/migration path;
- current v7 storage facts and constraints retain their meaning;
- current local SQLite development remains functional;
- existing local SQLite v7 data has a documented/tested safe transition path;
- storage callers retain equivalent behavior with minimal churn;
- the entire offline test suite passes;
- `./run.sh` remains offline and succeeds;
- no cloud infrastructure was created;
- no paid/provider calls were made;
- `prompts/018b-output.md` is written;
- Claude stops for review.

---

## Focus

> **Make persistence portable without changing what the data means or expanding into deployment.**
