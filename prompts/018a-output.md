# Step 018a — OpenAI vertical-slice gap analysis and architecture decision

_Date: 2026-11-03. No paid provider calls were made. No production Python, schema, or deployment changes were made._

---

## 1. Current OpenAI vertical-slice capabilities (from repository evidence)

### Exact provider / model / request profile

`openai.gpt-6-luna.v1` is registered in `llm_metrics/targets.py`:

| Field | Value |
|---|---|
| Model | `gpt-6-luna` |
| Endpoint | `POST https://api.openai.com/v1/responses` (SSE) |
| Settings sent | `store: false`, `reasoning.effort: "none"`, `prompt_cache_options.mode: "explicit"` |
| Cache policy | `disabled` |
| Key variable | `OPENAI_API_KEY` |

The profile is frozen (immutable dataclass), validated at construction, and pinned by `tests/test_targets.py`. Any accidental edit to the profile fails those tests.

### Workload selection

`python -m llm_metrics.real_benchmark --provider openai --workload interactive-chat-v1 --real` looks up the workload from `workloads.get_workload`, validates it against the catalogue SHA-256 pin, and refuses an unknown or mutated workload before making any network call. Default workload is `interactive-chat-v1` (cap 300, ~2K input tokens).

### One-request real benchmark command

`real_benchmark.run` → `benchmark.run_attempt` → `latency.measure_request` → `openai_provider.OpenAIProvider.stream` → `http_streaming.open_stream`. Exactly one HTTP request per invocation. `OneRequestPerAttemptTest` covers all four adapters.

### Streaming / TTFT semantics

`time.perf_counter()` from just before `open_stream` to the first `response.output_text.delta` event yielded to the caller. TTFT and total latency are independent measurements from the same timer start in a single pass.

### Token usage extraction

`usage.input_tokens`, `usage.output_tokens`, `usage.input_tokens_details.cached_tokens` from the `response.completed` / `response.incomplete` event. A missing or malformed usage block is `invalid_response`. No estimation from chunk counts.

### Provider request ID

`x-request-id` response header, captured by `StreamContext.set_request_id`, stored as `requests.provider_request_id`. Sanitized to `[A-Za-z0-9_.:-]` tokens; NULL when absent.

### Pricing / cost

`pricing.price_for("openai", "gpt-6-luna")` → `$0.10 input / $0.50 output / $0.01 cached per 1M tokens`, verified 2026-11-01. Rates stored per attempt. Cost = (input − cached) × input rate + cached × cached rate + output × output rate.

### Persistence behavior

`storage.save_request(db_path, request, results, "prod")` writes one `requests` row and up to four `observations` rows in a single `sqlite3` transaction. Either everything is saved or nothing. The database is at `data/llm_metrics.db` (git-ignored) on the local filesystem, schema version 7 (`PRAGMA user_version`).

### Real vs. simulated separation

`environment = "prod"` for real requests; `environment = "test"` for the simulated dummy provider. The analytics layer (`analytics.load_metric_window`, `load_benchmark_spend`) always takes an explicit environment and never mixes the two. The dashboard and API pages show one population at a time with explicit labels.

### Current HTML / API / dashboard support for real measurements

| Surface | Status |
|---|---|
| `/requests?data=real` | ✓ Shows all real `prod` request rows: tokens, latency, throughput, costs, profile, workload, origin. |
| `/spend?window=` | ✓ Shows real spend by provider/model. |
| `/` aggregate page | ✗ **Hardcoded** to `dummy` / `dummy-model-v1` / `test` in `query.AGGREGATE_PROVIDER`. Real OpenAI metric distributions not visible here. |
| `/api/v1/metrics` | ✗ **Hardcoded** to `dummy` / `dummy-model-v1` / `test` via `query.AGGREGATE_DATA = "simulated"`. |

The analytics machinery (`analytics.load_metric_window`) already accepts any `environment`/`provider`/`model`; only `query.py`'s fixed constants need to change to expose a real population selector.

### No-retry / no-fallback behavior

`http_streaming.open_stream` calls the opener exactly once. No code path retries, reroutes, or substitutes a model anywhere in the provider layer. `run_attempt` refuses a provider whose model or cache policy disagrees with its registered profile. Covered by `OneRequestPerAttemptTest`.

### Prior live-validation evidence

Two successful real runs (never repeated automatically):

| Date | Attempt id | Workload | TTFT | Total latency | Output tokens/s | Cost |
|---|---|---|---|---|---|---|
| 2026-10-30 | `44c889cb…` | `smoke.short_text.v2` | 3630.3 ms | 3880.7 ms | — | ~$0.000009 |
| 2026-11-03 | `9453a857…` | `interactive-chat-v1` | 4357.7 ms | 6753.8 ms | 119.0 tok/s | $0.000318 |

These are connectivity and path-validation runs, not benchmark results.

---

## 2. Evidence / gaps table

| Capability | Status | Notes |
|---|---|---|
| Registered OpenAI request profile | ✓ Present | `openai.gpt-6-luna.v1`; pinned by tests |
| One request per command, no retry | ✓ Present | Tested by `OneRequestPerAttemptTest` |
| Streaming TTFT semantics | ✓ Present | Validated live twice |
| Provider usage and request-id | ✓ Present | Validated by live run |
| Pricing verified and stored | ✓ Present | $0.10/$0.50/$0.01, verified 2026-11-01 |
| Real measurements persist to SQLite | ✓ Present | `environment = "prod"`, schema v7, tested |
| Real/simulated population separation | ✓ Present | All analytics respect environment |
| Real TTFT/latency visible in product | ✗ Gap | Aggregate page + API hardcoded to simulated dummy |
| Persistence survives process restart | ✓ (locally) | SQLite file persists on local disk |
| Persistence survives container restart | ✗ Gap | No persistent volume; ephemeral container filesystem |
| Schema migration portability | ✗ Gap | SQLite-specific `PRAGMA user_version`; not portable to Cloud SQL |
| Unattended runner (scheduler) | ✗ Gap | No loop, no cron, no Cloud Scheduler; every run is manual |
| Cloud execution / Cloud Run Job | ✗ Gap | No Dockerfile, no Cloud Run configuration |
| Secret handling (non-shell) | ✗ Gap | `OPENAI_API_KEY` set only in the shell; no Secret Manager integration |
| Scheduling / cadence / stop procedure | ✗ Gap | No bounded scheduler; no stop procedure |
| Cost / request-count guardrails | ✗ Gap | No budget cap; only protection is manual invocation |
| Production-origin recording | ✓ Partly | Config reads `LLM_METRICS_ORIGIN_CLOUD`/`REGION`; not yet set for GCP |
| Operational logging | ✓ Partly | `print` output; no structured Cloud Logging |
| Aggregate page for real data | ✗ Gap | Fixed to simulated dummy; needs provider/model selector |
| JSON API for real data | ✗ Gap | Fixed to simulated dummy |
| Production Flask serving (Gunicorn) | ✗ Gap | Werkzeug dev server only; not for production |

---

## 3. Minimum missing pieces for a bounded multi-day OpenAI experiment

Grouped by responsibility:

**Persistence durability and portability**
- The SQLite file must survive a container restart → persistent volume or managed database.
- The schema must be portable to Cloud SQL → SQLAlchemy Core + Alembic migration.

**Cloud execution runtime**
- A Dockerfile (or equivalent Cloud Run configuration) for the benchmark runner.
- `OPENAI_API_KEY` sourced from Cloud Secret Manager, not an environment variable set by hand.
- `LLM_METRICS_ORIGIN_CLOUD` / `LLM_METRICS_ORIGIN_REGION` set to the GCP region.

**Scheduling and guardrails**
- Cloud Scheduler job triggering a Cloud Run Job on an explicit cadence.
- Hard-coded maximum request count (e.g., 672 = 7 days × 4/hour) that stops the experiment.
- No automatic retries; each schedule trigger is exactly one attempt.

**Real-data analytics / API / dashboard**
- Provider/model population selector on the aggregate page and JSON API (code change only, no infrastructure).
- Production serving via Gunicorn (not Werkzeug's dev server) for the dashboard Cloud Run service.

**Not needed yet**
- Anthropic, Google, xAI onboarding
- PostgreSQL replication, read replicas, or multi-zone HA
- Authentication or CORS on the API
- Budget billing alerts (desirable but not blocking)
- Alerting / monitoring / structured metrics
- Public-facing deployment (dashboard remains private / team-only for now)

---

## 4. Recommended near-term Google Cloud architecture

```
Cloud Scheduler (cron: */15 * * * *)
        |
        | triggers on bounded schedule (max 672 runs)
        v
Cloud Run Job  (benchmark runner)
        |   Container: python -m llm_metrics.real_benchmark
        |              --provider openai
        |              --workload interactive-chat-v1
        |              --real
        |
        |   Env: OPENAI_API_KEY via Secret Manager
        |        LLM_METRICS_ORIGIN_CLOUD=gcp
        |        LLM_METRICS_ORIGIN_REGION=us-central1
        |        LLM_METRICS_DB_PATH=/cloudsql/...  (via Cloud SQL connector)
        |
        v
Cloud SQL  (PostgreSQL 16, db-f1-micro)
        |   One database, same schema as SQLite v7 (via SQLAlchemy Core + Alembic)
        |   Private IP; accessible by Cloud Run via Cloud SQL Auth Proxy
        |
        v
Cloud Run  (Flask web/API service)
        |   Container: python -m llm_metrics.web  (via Gunicorn)
        |   Same Cloud SQL connection
        |   CLOUD_SQL_CONNECTION_NAME in env
        |
        v
Dashboard + JSON API  (http://[cloud-run-url]/)
        /                    /api/v1/metrics
        /requests?data=real  /spend
```

**Why Cloud Run Job for the benchmark runner, not Cloud Run Service:**
A benchmark runner that executes one request and exits is naturally a Job (bounded execution), not a Service (always-on). Cloud Scheduler → Cloud Run Job is the canonical pattern for scheduled batch work on GCP.

**Why Cloud SQL PostgreSQL and not Cloud Spanner, BigQuery, or Firestore:**
- **Spanner**: overkill; designed for global multi-region consistency at high scale.
- **BigQuery**: append-only streaming, not OLTP; `UPDATE` is slow and expensive; poor fit for the per-attempt transaction model.
- **Firestore**: NoSQL; the relational schema with FK constraints, CHECK constraints, and JOIN queries fits SQL naturally, not a document store.
- **Cloud SQL PostgreSQL (db-f1-micro)**: the simplest managed relational database on GCP. At 96 requests/day (15-minute cadence, 7 days), this is trivially low volume. Estimated cost: ~$7–10/month for db-f1-micro. Fits the ≤$10/day budget easily.

---

## 5. Persistence recommendation: SQLAlchemy Core + Alembic

**Should it be adopted now?** Yes — for exactly the reason D066 stated: "adopt SQLAlchemy Core plus Alembic before production data exists; start Alembic at the v7 schema."

The Cloud SQL migration step (018b) is the right moment because:
- No production data exists in Cloud SQL yet (there is data in the local SQLite file, but it stays there for local development).
- A behavior-preserving migration step (no new features, just portability) is lower-risk when there is nothing to lose.
- Without SQLAlchemy Core, Cloud SQL would require either a new hand-written PostgreSQL-specific storage module or `psycopg2` calls embedded in the current `storage.py` — neither of which is better than the recommended path.

**What "SQLAlchemy Core" means here:**
- Table metadata with the same CHECK constraints (expressed as `CheckConstraint`).
- Explicit parameterized statements (no ORM, no lazy loading, no identity maps).
- `engine.begin()` replaces `with conn:` for the same all-or-nothing transaction semantics.
- `alembic upgrade head` replaces `_upgrade(conn)`.

**Migration scope for 018b:**
- Base Alembic revision = schema v7 (the current SQLite schema, expressed as SQLAlchemy metadata).
- Local SQLite path kept for tests (SQLite driver + SQLAlchemy is tested alongside PostgreSQL).
- `storage.connect()` becomes `storage.get_engine(db_url)`.
- All existing storage tests must continue to pass under SQLite.
- New tests run against the same schema via SQLite in-memory databases.

**Not needed in 018b:** Cloud SQL provisioning (that belongs in 018c); only the code and migration infrastructure.

---

## 6. Recommended next micro-step: 018b — SQLAlchemy Core + Alembic persistence migration

**Narrow objective:** Replace the SQLite-specific `storage.py` implementation with SQLAlchemy Core (same schema, same semantics, same tests) and add an Alembic migration whose base revision is the current v7 schema, so the storage layer can connect to Cloud SQL PostgreSQL in 018c.

**Files likely affected:**
- `llm_metrics/storage.py` — replace `sqlite3` with SQLAlchemy Core `Table`/`engine`/`Connection`; preserve all CHECK constraints, NULL semantics, and column names.
- `requirements.txt` — add `sqlalchemy` (Core only; pinned with sha256 hash).
- `scripts/install_requirements.py` — no change; it installs whatever is in `requirements.txt`.
- `alembic.ini` + `migrations/` — new Alembic environment; first revision = v7 schema.
- `tests/test_storage.py` — all existing tests must pass; add a test that the Alembic base revision matches the running schema.
- `DECISIONS.md` — record that D066 was adopted and the local SQLite upgrade chain is now legacy-only.

**Explicitly out of scope in 018b:**
- Cloud SQL provisioning (no GCP resources created).
- No new columns or schema changes.
- No change to `analytics.py`, `dashboard.py`, `api.py`, `web.py`, `benchmark.py`, or any provider.
- No change to any real benchmark command or workload.
- No paid provider calls.
- The local SQLite path must keep working (tests run against SQLite; `LLM_METRICS_DB_PATH` still works).

**Why this is the smallest dependency-unblocking step:**
All other cloud steps (Cloud Run Job, Cloud SQL, Cloud Scheduler, dashboard deployment) require the storage layer to be portable. Doing the SQLAlchemy migration in isolation — with no cloud resources created — is lower-risk than doing it simultaneously with the first Cloud Run deployment.

**Expected tests:**
- All 347 existing tests continue to pass (storage tests now use SQLAlchemy + SQLite in-memory or file).
- A new Alembic revision test: `alembic upgrade head` on an empty database and a v7 SQLite database both succeed.
- A test that the running schema matches the Alembic `head` revision.
- A fresh-process test that `storage` still imports without Flask/Werkzeug/Jinja.

**Requires paid/provider call?** No.

---

## 7. Proposed micro-step sequence

| Sub-step | Responsibility | Key constraint |
|---|---|---|
| **018a** | ✓ This gap analysis and architecture decision | No code changes |
| **018b** | SQLAlchemy Core + Alembic persistence migration | No cloud resources; local SQLite kept; all tests pass |
| **018c** | Cloud SQL provisioning + first Cloud Run deployment | Cloud SQL db-f1-micro; Cloud Run Job for benchmark runner; Secret Manager for API key; `LLM_METRICS_ORIGIN_CLOUD=gcp` |
| **018d** | Cloud Scheduler + bounded run loop + cost guardrails | One schedule trigger = one request; hard limit on total run count; stop procedure documented |
| **018e** | Real-data analytics/API/dashboard population selector | Code-only; no infra; aggregate page + `/api/v1/metrics` for real OpenAI population; labelled REAL PROVIDER DATA |
| **018f** | Cloud Run dashboard service deployment (Gunicorn) | Serve the same Flask app in production via Gunicorn; confirm pages show real data |
| **018g** | Bounded multi-day OpenAI experiment kickoff | Enable the Cloud Scheduler job; verify first few automatic attempts; operational review |
| **018h** | Data-quality and operations review | Inspect TTFT/latency/throughput series; failure classification; cost accumulation; dashboard/API agreement |
| **018i** | Marketing / publication checkpoint | Summary for growth/marketing workstream; methodology note; limitations; what is and is not publishable |

Each sub-step has one dominant responsibility and one clear review boundary before the next begins.

---

## 8. Risks and unknowns requiring user input

1. **Model availability recheck.** `gpt-6-luna` was verified 2026-11-01. Before any unattended run begins, the model page and pricing page should be rechecked. A model rename or price change requires a new profile version, not a silent edit.

2. **GCP project and billing.** No GCP project name, billing account, or region preference has been stated. 018c will need these before provisioning Cloud SQL or Cloud Run.

3. **Experiment cadence and budget confirmation.** The proposed values (15-minute cadence, 7-day duration, 672 max requests, ~$0.21 total API spend, ~$7–10/month Cloud SQL) need explicit approval. A decision to change them requires revisiting Phase D guardrails.

4. **Dashboard access policy.** After 018f, who can reach the Cloud Run dashboard URL? It should remain team-only (no public URL, Cloud IAP or similar). Decision needed before 018f.

5. **SQLAlchemy dependency size.** Adding SQLAlchemy Core adds ~3–4 MB (Core only, no ORM extras) and its transitive dependencies. If hash-pinning all new wheels is required by D057, this must be resolved in 018b before merging.

6. **`prompts/018-output.md` is the operational record.** It currently records only the OpenAI smoke result. After 018g starts, structured operational log entries (per-run summaries, failures, spend) should go there. Format to be defined.

---

## 9. Confirmation

- No paid provider calls were made in Step 018a.
- No production Python behavior, database schema, deployment files, or cloud resources were changed.
- Documentation changes made: `prompts/018a-output.md` (this file) and `PROJECT_STATUS.md` (updated "Next step" to reflect the new sequencing).
- `DECISIONS.md` not changed: D066 already records the SQLAlchemy recommendation; no new architectural decision beyond confirming it is now the right time.
