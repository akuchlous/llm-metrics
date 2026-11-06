# Step 018h output — Fail-closed paid cloud execution and durable-store decision

## Status: COMPLETE (2026-11-06)

Offline implementation only. No GCP resources created, changed, or executed.
No paid OpenAI or other provider calls. No secrets read or modified.
Style tools (pyink, isort, pylint) not available in this environment; not checked.

---

## Code changes

### `llm_metrics/real_benchmark.py`

Added `_CLOUD_APPROVED_DB_SCHEMES` module constant, `_check_cloud_db_url()` helper,
and a cloud-origin guard block inside `real_benchmark.run()`.

**Guard placement:** after `config.get_origin()` succeeds, before reading the API key
or constructing any provider adapter.

**`_check_cloud_db_url(raw_url: str) -> str | None`** — returns `None` if `raw_url`
is a valid cloud-approved URL (postgresql / postgresql+psycopg2), or a short
credential-free error message otherwise. Rejects: empty/unset, any `sqlite://` form,
bare paths (absolute, relative, `:memory:`), and unsupported schemes. Never echoes
the URL value.

**Guard in `run()`:**

```python
if origin[0] != config.DEFAULT_ORIGIN_CLOUD:
    raw_url = os.environ.get(config.DATABASE_URL_VARIABLE, "")
    url_error = _check_cloud_db_url(raw_url)
    if url_error:
        print(
            f"Error: {config.ORIGIN_CLOUD_VARIABLE}={origin[0]!r}:"
            f" {url_error} Cloud-origin paid requests require an explicit"
            f" PostgreSQL {config.DATABASE_URL_VARIABLE} to prevent data"
            " loss to ephemeral container storage. No request was made.",
            file=sys.stderr,
        )
        return 2
```

### `tests/test_cloud_db_guard.py` (new)

31 new offline regression tests covering:
- GCP origin + no URL → refuses before provider/network, even with fake API key
- GCP origin + `sqlite:///path`, `sqlite://:memory:`, bare absolute path, `:memory:`
- Unsupported scheme (mysql://)
- Other non-local origin (aws) + no URL → refuses
- Cloud origin + PostgreSQL URL → passes guard, reaches DB-preflight (unreachable DB → exit 2)
- Cloud origin + `postgresql+psycopg2://` → passes guard
- Local origin (empty or "local") + SQLite → NOT refused by guard, reaches existing preflight
- No credentials echoed in stdout/stderr for any case
- `_check_cloud_db_url()` unit tests for all URL forms

### `tests/test_openai_provider.py`

One test updated: `RealSmokeCommandTest.test_origin_comes_from_the_environment`.
The test previously used `LLM_METRICS_ORIGIN_CLOUD=gcp` without a PostgreSQL URL,
which now fails the cloud-origin guard. Fix: provide a fake `DATABASE_URL_VARIABLE=
postgresql://fake-host/test_db` in the env and patch `storage.connect` to redirect
to the existing SQLite test engine so save and read-back continue to work. Added
import of `llm_metrics.config` to the test file.

---

## Guard decision table

| Origin | DATABASE_URL | Scheme | Guard result |
|--------|-------------|--------|--------------|
| `local` (default) | any | any | Skipped — local SQLite behavior preserved |
| `gcp` | not set / empty | — | **Exit 2** — missing URL |
| `gcp` | `sqlite:///path` | `sqlite` | **Exit 2** — not durable |
| `gcp` | `sqlite://:memory:` | `sqlite` | **Exit 2** — not durable |
| `gcp` | `/absolute/path` | (no `://`) | **Exit 2** — bare path |
| `gcp` | `:memory:` | (no `://`) | **Exit 2** — bare path |
| `gcp` | `mysql://host/db` | `mysql` | **Exit 2** — unsupported scheme |
| `aws` | not set | — | **Exit 2** — any non-local cloud |
| `gcp` | `postgresql://host/db` | `postgresql` | Passes — existing DB-preflight runs |
| `gcp` | `postgresql+psycopg2://` | `postgresql+psycopg2` | Passes — existing DB-preflight runs |

After the guard passes, the existing `storage.connect()` preflight still verifies
the DB is reachable and the schema is ready before the paid call.

---

## Test evidence

**New focused tests:** 31/31 passed (0 failures).
**Full offline suite:** 423 tests run, 13 skipped (integration tests requiring
`TEST_POSTGRES_URL`), 0 failures.
**`./run.sh`:** tests passed, simulated measurement completed (`local / unknown`
origin; guard not triggered), dashboard startup failed only on port conflict
(port 8000 already in use in this environment — not a code regression).
**Style tools:** pyink, isort, pylint not available in this environment (optional
dev tools, not installed in `.venv` per D055). No style changes were made beyond
adding new code consistent with existing conventions.

---

## Limitations

**Old cloud image still unsafe:** the Cloud Run Job `llm-metrics-benchmark` runs
image `app:sha-9cf8ac9`, which predates this guard. The deployed container would
still fall back to SQLite if executed. This commit protects only code checked out
after this point.

**Non-executed safe steps for a later approved image update (do not run now):**

```bash
# In Cloud Shell, after provisioning a PostgreSQL DB and approving a new image:
gcloud builds submit --region us-central1 --tag \
  us-central1-docker.pkg.dev/llm-metrics-513617/llm-metrics/app:sha-$(git rev-parse --short HEAD)
gcloud run jobs update llm-metrics-benchmark --region us-central1 \
  --image us-central1-docker.pkg.dev/llm-metrics-513617/llm-metrics/app:latest
# Verify: gcloud run jobs describe llm-metrics-benchmark --region us-central1
```

**Origin is operator-declared:** the guard rejects configurations where the env
declares a non-local cloud but provides no PostgreSQL URL; it does not and cannot
verify that the runtime environment is actually a cloud container.

**SQLite-compatible PostgreSQL test:** the fix for `test_origin_comes_from_the_environment`
patches `storage.connect` globally during the test to redirect the fake PostgreSQL
URL to the SQLite test database. This is correct for testing origin-recording
semantics but would not catch PostgreSQL-specific behavior (the existing
integration tests in `test_postgres_integration.py` cover that).

---

## Durable-storage comparison (analysis only, no implementation)

Objective: preserve many small benchmark records for the next OpenAI-only pilot.
Reference: D069 (static public delivery, no always-on Flask service), D072 (pilot
backup), project `llm-metrics-513617` (us-central1).

Pricing sources used below: Google Cloud official pricing pages (checked 2026-11-06,
us-central1, standard tier, no sustained-use or committed-use discounts).
All costs are estimates; actual charges depend on transaction count and egress.

### Option A — Cloud SQL PostgreSQL (smallest instance, continuously provisioned)

**Configuration:** `db-f1-micro` (1 vCPU shared, 614 MB RAM), Enterprise edition,
PostgreSQL 17, us-central1, 10 GB SSD storage, no HA, no backups.

**Idle monthly cost:** ~$7–9/month for the instance plus ~$1.70 for 10 GB SSD
storage. Total: **~$9–11/month idle**, whether or not any benchmarks run.

**Per-run cost:** negligible beyond the idle cost (a few milliseconds of CPU for
one INSERT).

**Implementation complexity:** None beyond what is already proven — the 018f pilot
ran this exact configuration; the SQLAlchemy/Alembic stack connects and migrates
without changes.

**Data durability:** high — Cloud SQL manages replication, point-in-time recovery
(configurable), and automated backups. Alembic schema history is preserved.

**Migration / queries / analytics:** full SQL; existing analytics, spend, and
dashboard queries run unchanged. The 018f CSV export can be re-imported
(`\copy requests FROM 'requests.csv' CSV HEADER`; observations after in FK order).

**Cloud-job security:** the job needs `roles/cloudsql.client` (already on
`llm-metrics-job@`) and `LLM_METRICS_DATABASE_URL` from Secret Manager.

**What is proven vs. hypothetical:** fully proven in 018f. The pilot executed one
real request and stored it in this exact configuration before Cloud SQL was deleted.

**Gap:** idle cost (~$9–11/month) is real even when no benchmark runs. At one or
two benchmark sessions per month the per-session cost of the DB is high relative
to the ~$0.0003/request API cost.

---

### Option B — Cloud Storage object-based append-only results store

**Concept:** each benchmark run writes a small JSON or CSV file (one file per run,
or one file per batch) to a private Cloud Storage bucket; a separate export/publish
step reads all files and produces the static HTML/JSON snapshots (D069).

**Idle monthly cost:** ~$0.02/GB/month (Standard, us-central1). At 1 KB per run,
one thousand runs ≈ 1 MB ≈ **~$0.00002/month**. Effectively free at pilot scale.

**Per-run cost:** one `storage.objects.insert` call. Egress for a typical run is
under 10 KB. Total: **under $0.001/run** (storage write + negligible egress).

**Implementation complexity:** significant. The existing storage interface
(`storage.save_request`, `storage.load_observations`) is SQLAlchemy SQL — it cannot
write to Cloud Storage without a new storage backend. Required changes:
- New `gcs_storage.py` module with `save_request` → writes JSON file to GCS.
- Deduplication: append-only files have no UNIQUE constraint; a replay must be
  idempotent (use attempt UUID as filename: `<id>.json`).
- Atomicity: a single Cloud Storage object PUT is atomic at the object level, but
  a run that writes the request JSON then crashes before writing observations
  leaves a partial record. A single-document format (request + observations) avoids
  this if written as one atomic object.
- Retries: a failed PUT must be retried; the existing no-retry policy on HTTP
  streaming would need a separate retry wrapper for the storage write.
- Concurrent writes: safe — each run writes a separate object keyed by UUID.
- Historical analysis: requires downloading all objects and loading into memory or
  a local SQLite DB; ad-hoc SQL analytics not available without an ETL step.
- Backup/restore: objects are versioned if versioning is enabled (as in the 018f
  backup bucket). Restore = re-download all objects.
- Dashboard: the existing Flask dashboard would need a new read path or would be
  disabled; analytics rely on `load_observations` which uses SQL.

**What is proven vs. hypothetical:** the 018f backup bucket uses Cloud Storage, but
only as an archive of CSV exports — the SQLAlchemy write path was PostgreSQL, not
GCS. A direct GCS write path is entirely hypothetical and untested.

**Gap:** the implementation effort is large (new storage abstraction, new read path
for analytics, deduplication, retry, format design). Incompatible with D069's
requirement for a static publish step unless a separate aggregation pipeline is
built. Not viable as a drop-in replacement without significant new code.

---

### Option C — Serverless SQL alternative (on-demand / auto-scaling)

**Requirement:** genuinely usable with the existing SQLAlchemy/PostgreSQL interface
without code changes.

**Candidates evaluated:**

- **Cloud Spanner:** PostgreSQL-compatible interface (`SPANNER_EMULATOR_HOST`), but
  not wire-protocol compatible with psycopg2/SQLAlchemy's standard PostgreSQL
  dialect. Requires the Spanner client library. Pricing: ~$0.90/node-hour
  (10-node minimum for production). Not viable at this scale.
- **AlloyDB Serverless (GCP):** announced in preview. As of the knowledge cutoff,
  pricing and psycopg2 compatibility were not confirmed in generally available
  documentation. Cannot be recommended without confirmed pricing and a verified
  connection test.
- **Neon (third-party PostgreSQL-compatible serverless):** genuine scale-to-zero,
  psycopg2-compatible, free tier available. Not GCP-native; data would leave the
  GCP project; no GCP-managed access control or VPC integration. Viable technically
  but introduces a third-party data dependency.
- **Cloud SQL with start/stop automation:** not serverless; a stopped instance
  is not billed for compute but still billed for storage. Starting it before a run
  and stopping after adds ~2 minutes of latency and operational complexity.

**Conclusion:** no GCP-native serverless PostgreSQL option is currently confirmed
usable with the existing SQLAlchemy/psycopg2 interface without code changes.
AlloyDB Serverless is the most plausible future candidate but is unconfirmed.

---

### Summary comparison

| | Cloud SQL (A) | Cloud Storage (B) | Serverless SQL (C) |
|---|---|---|---|
| Idle monthly cost | ~$9–11 | ~$0 | Unconfirmed |
| Per-run cost | ~$0 | ~$0.001 | Unconfirmed |
| Implementation effort | None (proven) | Large (new backend) | Unconfirmed |
| Data durability | High | High (versioned objects) | Unconfirmed |
| Existing analytics | Unchanged | Requires ETL | Unconfirmed |
| 018f CSV importable | Yes | Yes (new read code) | Unconfirmed |
| Proven in this project | Yes (018f) | No | No |

---

### Recommended smallest next step

**Provision a new Cloud SQL `db-f1-micro` instance for the next benchmark session;
tear it down immediately after the session and backup the data.**

Rationale: Cloud SQL is the only fully proven option (018f). The ~$9–11/month idle
cost is high, but it disappears if the instance is deleted between sessions (as in
018f). At one or two benchmark sessions per month, the total cost per session is
controlled. No code changes are needed beyond the guard already added in 018h.
Cloud Storage could reduce idle cost but requires substantial new code; AlloyDB
Serverless is not yet confirmed viable.

This matches the locked product direction (D069): static public HTML and JSON
snapshots are generated from the collected data, not from a continuously running
database. A per-session Cloud SQL instance is sufficient for collection; the
export/publish pipeline is a separately scoped step.

---

## GCP resources and spend

No GCP changes in this step. Ongoing cost unchanged from 018g: ~$0.13/month.
Cloud Run Job still vulnerable to SQLite fallback if executed (old image).
No paid API calls.

---

## Design Q&A

**Q: Why is the guard placed before the API key check rather than after?**

A: Placement before the API key check ensures the guard fires even when no key is
configured (e.g. a misconfigured Cloud Run Job with environment variable missing).
More importantly, it enforces the principle that configuration errors about durable
storage are categorically distinct from and logically prior to provider credential
errors: a job with no DB URL is not ready to run, regardless of whether a key is
present.

**Q: Why not make the guard part of `config.get_database_url()`?**

A: `config.get_database_url()` is a general accessor used by the dashboard, local
dev, and simulated tests — none of which should be blocked by a PostgreSQL
requirement. The guard is a business rule specific to paid execution from a cloud
origin. Mixing it into the config accessor would impose the cloud restriction on all
code paths. The rule belongs at the boundary where money is spent (`real_benchmark.run`).

**Q: Does the guard protect the currently deployed Cloud Run Job?**

A: No. The job runs image `app:sha-9cf8ac9`, which predates this commit.
Until the image is rebuilt with the new code and redeployed, the existing job would
still fall back to SQLite. Do not execute the existing job.

---

## MARKETING CHECKPOINT: not publishable yet

n=1 real request, single provider, single region, no recurring dataset.

---

## Recommended next micro-step

**Step 018i:** Provision a new Cloud SQL `db-f1-micro` instance for the second
benchmark session (OpenAI only); rebuild and redeploy the Cloud Run Job image with
the 018h guard; run one new measurement; verify the guard fires if DB URL is absent;
export and back up the results; delete Cloud SQL. No new providers, no scheduling.
