# Step 018d Output — Real PostgreSQL Integration Proof and Safe Migration Gate

**Date:** 2026-11-03
**Prompt:** `prompts/018d-postgresql-integration-and-migration-safety.md`
**Status:** Complete — 376 tests total (363 offline; 13 integration), `./run.sh` verified
**PostgreSQL version used:** 17.11 (Debian 17.11-0+deb13u1), localhost, disposable database `llm_metrics_018d`

---

## What was done

### Integration harness

`tests/test_postgres_integration.py` — skipped unless `TEST_POSTGRES_URL` is set. Refuses URLs with a hostname other than `localhost` or `127.0.0.1`. Each test drops `observations`, `requests`, and `alembic_version` in `setUp` and disposes the engine in `tearDown`. No credentials appear in test source, output, or assertions.

Run with:
```
TEST_POSTGRES_URL=postgresql://user:pass@localhost/dbname \
    python -m unittest tests.test_postgres_integration -v
```

### Changed files

| File | Change |
|------|--------|
| `llm_metrics/storage.py` | `_redact_db_url()`, fail-closed PG orphan tables, connection-via-attributes to Alembic, engine dispose on `_ensure_schema` failure, `spend_by_model` ORDER BY fix |
| `tests/test_postgres_integration.py` | New: 13 integration tests + 4 `_redact_db_url` unit tests |
| `DECISIONS.md` | D067 added |
| `PROJECT_STATUS.md` | Current state updated to 018d |
| `design-questions/018d/` | Four role-specific files + README row |
| `prompts/chatgpt-conversation.md` | 018d entry appended |

---

## PostgreSQL test matrix (PostgreSQL 17.11, localhost)

| Test | Result |
|------|--------|
| Fresh DB: v7 tables, indexes, FK, and Alembic revision row | pass |
| Successful request + observations round-trip | pass |
| Failed request: NULL tokens/cost, no observations | pass |
| CHECK constraint violation → `IntegrityError` | pass |
| FK violation (delete request with observations) → `IntegrityError` | pass |
| Atomic rollback: CHECK fails → nothing saved | pass |
| Environment isolation (test vs prod rows) | pass |
| Cache-policy filtering | pass |
| Spend aggregation (1 success + 1 failure) | pass |
| `ON CONFLICT DO NOTHING` seeding idempotency | pass |
| Reconnect and data durability | pass |
| Readable timestamps (Z suffix), newest-first ordering | pass |
| Orphan tables (no alembic_version) → `RuntimeError`, no URL leak | pass |

**Command used:**
```
TEST_POSTGRES_URL=postgresql://llm_metrics_test:test_pw_018d@localhost/llm_metrics_018d \
    python -m unittest tests.test_postgres_integration -v
```
Result: `Ran 17 tests in 0.842s — OK`

---

## Migration safety decision (D067)

### Fix 1: Fail-closed orphan-tables behaviour

**Before:** `_ensure_schema()` silently called `alembic stamp head` for any PostgreSQL database with application tables but no `alembic_version` row, trusting the schema was correct.

**After:** Raises `RuntimeError` with a sanitized, actionable message. The operator must inspect the schema and run `alembic stamp <revision>` manually.

### Fix 2: Credentials out of Alembic config strings

**Before:** `alembic_cfg.set_main_option("sqlalchemy.url", str(engine.url))` set the full URL as a config string. This (a) exposed the URL in Alembic's config-level log output, (b) triggered Python's `ConfigParser` interpolation on percent-encoded password characters (e.g. `%40` in a URL-encoded `@`), and (c) embedded credentials in any config-level error messages.

**After:** `alembic_cfg.set_main_option("script_location", ...)` is the only option set. A live connection is passed via `alembic_cfg.attributes["connection"]`; `env.py`'s existing `config.attributes.get("connection")` path uses it directly. No URL string is ever written into the Alembic config.

### Fix 3: `spend_by_model` strict-GROUP-BY correctness

**Before:** `ORDER BY r.c.total_cost.is_(None)` — a bare column reference in ORDER BY while using GROUP BY. SQLite accepts this (permissive); PostgreSQL refuses it.

**After:** `ORDER BY func.sum(case((is_success, r.c.total_cost), else_=None)).is_(None)` — the same aggregate expression used in the SELECT clause, valid under PostgreSQL's strict GROUP BY rules.

---

## Credential safety evidence

- `_redact_db_url(url)` strips `user:password@` before the host; 4 unit tests pass (with credentials, percent-encoded credentials, without credentials, SQLite URL).
- Orphan-tables `RuntimeError` message verified to contain neither `@` nor the test URL.
- Alembic config never contains `sqlalchemy.url`; `env.py`'s credential-bearing code path (`create_engine(url)`) is only reached when `config.attributes["connection"]` is absent, which is never the case from `_ensure_schema()`.
- `psycopg2` authentication-failure errors do not include the password in their message (`FATAL: password authentication failed for user "xxx"`).

---

## SQLite regression results

All 359 existing SQLite tests pass unchanged. `./run.sh` output:
```
✓ Python environment ready
✓ Dependencies ready
✓ Tests passed
Simulated TTFT history: 0 new, 168 already present
Database: data/llm_metrics.db
✓ Simulated history ready
✓ Starting test measurement
```

---

## Test counts

| Scope | Count | Note |
|-------|-------|------|
| Offline suite (`./run.sh`, no `TEST_POSTGRES_URL`) | 376 | 13 skipped |
| Integration (PostgreSQL 17 localhost) | 17 | 13 class + 4 unit |
| Total unique tests | 376 | |

---

## MARKETING CHECKPOINT

**Not publishable yet.** Step 018d is an internal correctness and safety step — no user-visible feature, no cloud database, no deployed service. The project remains a local development tool. No marketing claim is appropriate at this stage.

---

## Risks and limits

- Integration tests use a local PostgreSQL 17 instance created for this step (`llm_metrics_018d`). Cloud CI would need `TEST_POSTGRES_URL` set in the CI environment and a PostgreSQL service container.
- Only the Linux x86_64 cp313 wheel hash is pinned for `psycopg2-binary==2.9.10`; other platforms need additional hash entries.
- Production migration management (running `alembic upgrade head` before routing traffic) remains the operator's responsibility; per-connection auto-migration is only appropriate for the single-revision baseline.
- No GCP resources created; no paid API calls; no automatic scheduler.

---

## Design Q&A summary

**Q (lead):** What made `r.c.total_cost.is_(None)` work in SQLite but not PostgreSQL?  
**A:** SQLite does not enforce that ORDER BY expressions be aggregates when GROUP BY is used. PostgreSQL's strict GROUP BY requires every ORDER BY column to be either in the GROUP BY clause or wrapped in an aggregate. The fix uses the same `func.sum(case(...))` expression from the SELECT clause in the ORDER BY.

**Q (principal):** Why pass the connection via `config.attributes["connection"]` instead of setting `sqlalchemy.url`?  
**A:** (1) Keeps the credential-bearing URL string out of Alembic's config serialization and any config-level log lines. (2) Avoids Python's `ConfigParser` interpolation on percent-encoded password characters like `%40`. (3) The connection is already open and validated; Alembic doesn't need to re-establish it.

---

## No GCP spend confirmation

No Cloud SQL instances, Cloud Run services, Secret Manager secrets, or any other billable GCP resources were created or modified. PostgreSQL 17 was installed locally (apt-get) and used on localhost only.

---

## Commit

See `git log` for the 018d commit SHA.

## Recommended next step

Step 018e: provision Cloud SQL PostgreSQL, set `LLM_METRICS_DATABASE_URL` pointing to it in the deployment environment, run `alembic upgrade head` as a pre-traffic migration step in Cloud Run, and deploy the scheduler and web server. Authorize with a separately reviewed prompt.
