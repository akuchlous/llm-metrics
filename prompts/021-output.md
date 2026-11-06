# Step 021 output — Durable append-only benchmark result storage (offline, GCS-ready)

## Status: COMPLETE (offline only)

An immutable, single-object-per-attempt JSON record format, a create-only Google Cloud Storage writer with bounded storage retries and reconciliation, and a read/validate path are implemented and tested **offline**. Nothing is wired into the paid execution path. **No GCP resource was created or changed, no `gcloud` command was run, no paid provider request was made.** The guarded Cloud Run Job remains credential-disabled, DB-less and idle on digest `sha256:1b67b96f…` (Step 020). Step 021 does **not** enable cloud collection.

---

## What was implemented

| File | Change |
|---|---|
| `llm_metrics/object_results.py` | **New.** Record builder (`build_record`), validator (`validate_record`), canonical encoder/decoder (`encode_record`, `decode_record`), object naming (`object_name`), target validation (`ResultTarget`, `target_from_environ`), narrow `ObjectStore` protocol, create-only writer (`write_record`), reader (`read_record`), SQL-row mapping (`to_storage_rows`, `from_storage_rows`), and `GcsObjectStore` (google-cloud-storage adapter). |
| `tests/test_object_results.py` | **New.** 43 offline tests (below). |
| `requirements.txt` | Added `google-cloud-storage==3.17.1` and its complete transitive closure (20 packages), hash-pinned. |
| `tests/test_install_requirements.py` | Expected package set extended with the 20 new packages. |
| `prompts/021-output.md`, `design-questions/021/*`, `design-questions/README.md`, `PROJECT_STATUS.md`, `DECISIONS.md` (D078), `prompts/chatgpt-conversation.md` | Completion artifacts. |

**Unchanged (verified by `git diff`):** `benchmark.py`, `real_benchmark.py` (incl. `_check_cloud_db_url()`), `real_smoke.py`, `storage.py`, `config.py`, provider adapters, migrations, `Dockerfile`, `Dockerfile.dev`, `compose.yaml`, `run.sh`. A test (`BoundaryTest.test_paid_path_does_not_use_object_results`) fails if `benchmark.py`, `real_benchmark.py` or `real_smoke.py` ever references `object_results`.

## Record format (schema `llm-metrics.attempt.v1`)

One object = one attempt: request facts + all its metric observations. Example with **synthetic, non-sensitive data** (actual canonical bytes; 879 bytes; a failure record is ~700 bytes):

```json
{"attempt_id":"0123456789abcdef0123456789abcdef","environment":"prod","observations":[{"metric":"total_latency","value":2500.5},{"metric":"ttft","value":400.25},{"metric":"output_tokens_per_s","value":95.0},{"metric":"output_chunks_per_s","value":90.5}],"recorded_at":"2026-11-06T12:00:00.000001Z","request":{"cache_policy":"disabled","cached_input_price_per_1m":0.01,"cached_input_tokens":0,"failed_after_ms":null,"input_cost":0.0001,"input_price_per_1m":0.1,"input_tokens":1000,"model":"gpt-6-luna","origin_cloud":"gcp","origin_region":"us-central1","outcome":"success","output_cost":0.0001,"output_price_per_1m":0.5,"output_tokens":200,"provider":"openai","provider_request_id":"req_synthetic_0001","request_profile_id":"openai.gpt-6-luna.v1","requested_max_output_tokens":300,"total_cost":0.0002,"workload_id":"interactive-chat-v1"},"schema_version":"llm-metrics.attempt.v1"}
```

Object name: `<prefix>/v1/requests/<environment>/<UTC date of recorded_at>/<attempt_id>.json`, e.g. `attempts/v1/requests/prod/2026-11-06/0123456789abcdef0123456789abcdef.json`.

**Contracts:**
- **Identity:** `attempt_id` is llm-metrics' own random UUID hex (same as `requests.id`); the provider request id is a fact inside the record, never in the name. The name is a pure function of the record (environment, date, id), and `decode_record(..., expected_name=…)` rejects an object stored under a name it does not belong to.
- **Time:** `recorded_at` is `storage.format_timestamp` text (UTC, fixed width, `Z`), validated as a real date.
- **Facts:** `request` holds exactly the 20 `storage` requests-table columns other than `id/recorded_at/environment` (`REQUEST_FIELDS`, frozen with v1; a test pins it against `storage._REQUEST_COLUMNS`). Observations hold `metric` (a `latency.METRICS` key, which fixes the unit: ms, ms, tokens/s, chunks/s) and `value`, in `latency.METRICS` order; provider/model/time/environment/request id are the parent's, as `storage.save_request` writes them.
- **Null semantics:** unknown = JSON `null`, never 0. Validation mirrors `ck_requests_outcome_consistency`: success ⇒ tokens and costs known, `failed_after_ms` null, `total_latency` and `ttft` present; failure ⇒ tokens, costs and cached tokens null, `failed_after_ms` set, no observations. Also enforced: known outcome, cache policy (not legacy `unknown`), non-negative integer counts, finite non-negative float amounts, `cached_input_tokens ≤ input_tokens`, `output_tokens ≤ cap`, required non-empty workload/origin/profile.
- **Exclusions:** the builder copies named fields only, so prompts, responses, provider `diagnostics`, headers, keys, DB URLs cannot enter a record (tested with each).
- **Canonical encoding:** UTF-8 JSON, sorted keys, `(",", ":")` separators, `allow_nan=False`; integral amounts normalized to float so `1` and `1.0` encode identically. The decoder rejects non-canonical bytes, duplicate keys, NaN/Infinity, non-UTF-8.
- **Versioning:** `schema_version` must equal `llm-metrics.attempt.v1`, and the path carries `v1`. A future schema gets a new version string and path segment; v1 objects are never rewritten.

## Writer: create-only, idempotent, bounded

`write_record(store, target, record, max_attempts=3)`:

1. Validate and encode; compute name and SHA-256.
2. `store.create` (GCS: single multipart upload with `ifGenerationMatch=0` and the content `md5Hash`, client-library retries disabled with `retry=None`). The server refuses to overwrite and rejects corrupted bytes.
3. Read the object back and compare bytes.
   - Created and identical ⇒ `WriteResult(created=True)`.
   - Already existed (HTTP 412) and identical ⇒ `created=False`. This is the idempotent replay, or our own earlier attempt whose acknowledgement was lost.
   - Already existed and different ⇒ `RecordConflictError`; the existing object is untouched.
   - Created but read-back differs or is absent ⇒ `RecordIntegrityError`.
4. Transient failure (408/429/5xx, connection reset or timeout) on create or read ⇒ back off 0.5 s then 2.0 s and repeat. The next create-only call decides the ambiguous case: if the server had committed the object, we get 412, then a matching read. This never produces a second object and never overwrites.
5. Retries exhausted ⇒ `StoreUnavailableError("… record not confirmed durable …")`.
   - Permanent errors (403, 400, …) are raised immediately, without retry.
   - A permanent error on the read-back after a confirmed create leaves durability unknown, and is raised as such.

**Storage retries are not provider retries:** the writer only ever receives a finished measurement and has no access to providers.

**Targets:**
- Bucket and prefix must be configured explicitly (`LLM_METRICS_RESULTS_BUCKET`, `LLM_METRICS_RESULTS_PREFIX` via `target_from_environ`; no defaults). Nothing reads these variables yet.
- **Bucket:** must follow GCS naming. Dotted or domain buckets, and names starting `goog` or containing `google`, are refused.
- **Prefix:** must be lowercase segments, with no `.`/`..`, no empty segments and no leading or trailing `/`. The `snapshots/...` prefixes are reserved, so records can never land among the pilot backups.
- No public URL is produced or returned.

**Errors:** all messages carry an object name or field name only. GCS errors are translated to the exception class plus HTTP code, with `from None`, so response bodies and transport messages are never chained or printed (tested with a body containing `SECRET-BODY` and a connection error containing `token=abc`).

**Library behaviour found during testing:** `google-cloud-storage` 3.17 starts a best-effort **background bucket-metadata GET** (`_bucket_metadata_cache`) the first time a bucket is used. On 403 it caches fallback values and continues, so the upload still works without `storage.buckets.get`. It is one extra read operation per process and doesn't affect correctness; it should be accounted for when designing IAM in Step 022.

## Read / restore path

- `read_record(store, target, name)` returns a validated record. It refuses names outside the prefix, missing objects (`ResultStoreError`), and objects whose content doesn't match the name.
- `to_storage_rows(record)` rebuilds the exact `requests` row (all 23 columns) and the `observations` rows (all columns except the database-assigned integer `id`).
- `from_storage_rows(...)` is the inverse, for importing an existing attempt with its original id and time.

**Future aggregation (described, not implemented):** for a time window,
1. list `…/v1/requests/<env>/<date>/` for each date in the window (date partitioning bounds the listing);
2. decode and validate each object, and filter by `recorded_at`;
3. feed `to_storage_rows` output into the existing analytics, e.g. an ephemeral SQLite or in-memory computation, then build static snapshots per D069.

Duplicates can't arise, because the id is the name; a conflicting object is never created.

**Importing the 018f/020 CSV snapshots (described, not implemented):**
1. Download a verified snapshot read-only and check `SHA256SUMS`.
2. Type the CSV columns: empty cells become `null`.
3. Call `from_storage_rows` per attempt, then `write_record` under the records prefix with the original ids and timestamps. Create-only writes can't touch the originals, and the reserved `snapshots/` prefix blocks writing among them.

The exact Step 020 row, with the values verified from PostgreSQL in `prompts/020-output.md`, round-trips byte-for-byte through `from_storage_rows → encode → decode → to_storage_rows` (tested). The 018f row has the same 23-column schema, but its exact values weren't re-read: that is private data, and the prompt forbids downloading it. Its import is therefore untested beyond schema shape.

## Tests run (all offline)

Docker `./run.sh test` was run twice on the final tree:

| Run | Tests | Skipped | Failures | PostgreSQL integration | Dashboard | Leftovers |
|---|---|---|---|---|---|---|
| 1 | 487 | 5 | 0 | executed (24 integration-module tests ok) | HTTP 200 | 0 containers, 0 volumes |
| 2 | 487 | 5 | 0 | executed (24 ok) | HTTP 200 | 0 containers, 0 volumes |

- **Counts:** 487 = 444 (Step 020) + 43 new.
- **Skips:** the same 5 as before (`test_container_config` ... `skipped outside repo root`). No new skips.
- **No state dependence:** the second run's results were identical to the first.

**New tests (`tests/test_object_results.py`, 43):**
- **RecordShapeTest (8):**
  - a complete single record with exact values
  - exact JSON round trip
  - failure nulls kept, `diagnostics` dropped
  - prompt, response, key, DB URL and headers excluded
  - omitted optional facts become null
  - deterministic canonical bytes (key order, observation order, int vs float)
  - `REQUEST_FIELDS` equals the storage columns
  - metric names and units come from `latency.METRICS`
- **ValidationTest (8):**
  - rejects other schema versions, wrong shapes and missing/extra keys
  - rejects bad ids, timestamps (including 2026-02-30) and environments
  - rejects 19 invalid fact cases: NaN/Inf, negatives, bools, unknown cache policy, cached > input, output > cap, …
  - rejects failures carrying success facts
  - rejects invalid observations: duplicates, unknown metric, wrong order, missing ttft or total latency, extra keys
  - the builder rejects missing facts and observations from a different model
  - the decoder rejects non-canonical, duplicate-key, NaN, empty, array and non-UTF-8 input
  - error messages contain no values
- **TargetAndNameTest (3):** the name format (no provider request id in it); 18 unsafe bucket/prefix cases; environment variables must be set explicitly.
- **WriterTest (12):**
  - exactly one object is created
  - an identical replay is idempotent
  - a conflicting payload is rejected and the original is untouched
  - concurrent writers can't overwrite each other
  - a transient error before the create is retried
  - a lost acknowledgement (object committed, then 503) is reconciled with no second object
  - retries are bounded (sleeps 0.5 and 2.0 s), and the error says "not confirmed durable"
  - a permanent error is not retried
  - a read-back mismatch, or an object that disappears, raises an integrity error
  - a transient read-back error is retried and reconciled
  - an invalid record writes nothing
  - error messages contain no record content
- **ReadTest (2):** read back into SQL rows without loss; rejects names outside the prefix, missing objects, and objects moved to another date.
- **StorageCompatibilityTest (3):**
  - A real `benchmark.run_attempt` with the OpenAI adapter over a fake HTTP opener (cached tokens 8, `x-request-id`), stored in SQLite: the record's `to_storage_rows` **equals the stored SQL row** and metrics.
  - The same for a failed dummy-provider attempt (null costs, no observations).
  - The exact Step 020 measurement round-trips.
- **GcsObjectStoreTest (5):** these use the **real google-cloud-storage client** over a fake HTTP session, under `no_network`.
  - The upload is `POST …/b/<bucket>/o?uploadType=multipart&ifGenerationMatch=0` with `md5Hash` and `application/json`.
  - 412/503/429/500/connection reset/403/400 map to the right error types, with sanitized messages and no chained cause.
  - A read returns bytes, `None` on 404, and a transient error on 503.
  - A lost acknowledgement end to end through the client (commit + 503, then 412, then a matching read) succeeds.
  - A conflict end to end through the client is rejected.
- **BoundaryTest (2):** importing `object_results` doesn't load `google.cloud.storage` (checked in a subprocess); the paid-path modules don't reference `object_results`.

**Other checks:**
- **Dependency set:** the candidate `requirements.txt` was installed in clean `python:3.13-slim` with `pip --require-hashes --only-binary=:all: --isolated`. `pip check` reported no broken requirements, and nothing outside the list was needed.
- **Production image smoke** (local build, not pushed):
  - The guard still refuses gcp-origin without PostgreSQL (exit 2, "No request was made").
  - `import llm_metrics.object_results` works and doesn't load the GCS client.
  - `google.cloud.storage` 3.17.1 is importable.
  - The image is still non-root (uid 1000) with no `tests/`.
  - Size went from about 259 MB to 327 MB uncompressed (the base image was also re-pulled, so the delta is approximate).
- **Style:** pyink, isort (`--profile google`) and pylint (`.pylintrc`) ran in a throwaway container, since they're not installed in `.venv`. The new and changed files are clean.
  - **Older findings, untouched:** across the repo, pyink reports 12 files that would be reformatted and isort flags imports in 4 files. Both counts are identical on the Step 020 baseline.
- **ResourceWarnings:** the new tests run clean under `-W error::ResourceWarning`, because they dispose the SQLite engines they create.

**What this does NOT verify:** passing tests with a fake transport is **not** a live GCS durability test. Not exercised:
- real IAM
- a real bucket and its retention settings
- real network failure timing
- real server-side MD5 rejection
- Application Default Credentials on Cloud Run

## Dependency changes

- **Added:** `google-cloud-storage` 3.17.1, plus google-cloud-core 2.8.0, google-api-core 2.43.0, google-auth 2.62.0, google-resumable-media 2.11.0, google-crc32c 1.9.0, googleapis-common-protos 1.76.0, protobuf 7.36.2, proto-plus 1.29.0, opentelemetry-api 1.45.1, requests 2.34.2, urllib3 2.8.0, certifi 2026.10.23, charset-normalizer 3.5.2, idna 3.20, cryptography 50.0.2, cffi 2.1.1, pycparser 3.12, pyasn1 0.6.4 and pyasn1_modules 0.4.2.
- **Pinning:** every version was released on or before 2026-10-23, at least two weeks before it was chosen. Only Linux x86_64 cp313/abi3 wheels and pure-Python wheels are pinned.
- **Why a library:**
  - Application Default Credentials, token refresh and the GCS upload protocol are commodity, security-sensitive code (CODING_GUIDELINES "reuse").
  - The provider adapters avoid SDKs (D064) because SDK retries and fallbacks would corrupt measurement. Here, client retries are disabled explicitly (`retry=None`), and the writer owns the retry policy.
- **Production image:** the module ships in the production image, so its dependency must be there too. The image wasn't rebuilt or deployed in the cloud.
- **Cost of the choice:** a larger dependency tree (cryptography, protobuf) and about 69 MB more image. `google-cloud-storage` has no import-time network access, and it's imported lazily.

## Volume and cost estimates (to be rechecked before activation)

Assumptions:
- **Prices:** Standard storage about $0.020/GB-month; Class A (writes, lists) $0.005 per 1,000; Class B (reads) $0.0004 per 1,000. The us-central1 Always Free tier covers 5 GB-months, 5,000 Class A and 50,000 Class B operations a month.
- **Operations per attempt:** 1 create (Class A) + 1 read-back (Class B). Each process also does 1 bucket-metadata GET (Class B).
- **Size:** about 0.9 KB per record.

| Cadence | Objects/month | Storage after 1 year | GCS cost/month (no free tier) | With free tier |
|---|---|---|---|---|
| 1 model hourly (24/day) | ~720 | ~8 MB | ~$0.004 | $0 |
| 1 model every 15 min (96/day) | ~2,880 | ~32 MB | ~$0.017 | $0 |
| 4 models every 15 min (384/day) | ~11,520 | ~125 MB | ~$0.068 | ~$0.03 |

**Context, not part of this step:**
- **Always-on Cloud SQL:** `db-f1-micro` is about $9.40/month idle. GCS records have **no always-on database cost**.
- **Cloud Run Job time** is the bigger cost driver. Step 020's execution ran about 80 s including startup. At 96/day that's about 230k vCPU-s/month, near the 240k free tier; at 384/day it's about $10–13/month beyond the free tier.
- **OpenAI** `gpt-6-luna` costs about $0.00033 per attempt, so about $0.95/month at 96/day.
- All of this stays far below $10/day.

**Lifecycle and retention:**
- Records are append-only and kept indefinitely. Cost grows about linearly and stays tiny.
- A bucket retention policy or Bucket Lock could make deletion impossible as well. That's a Step 022+ decision.
- Soft delete only matters for deleted objects.
- No lifecycle deletion rule is recommended for measurement records.

## Remaining risk: between a paid response and a durable object

A GCS preflight before the provider call can check configuration and permissions. It **cannot guarantee** that the write after the response succeeds, so the risk stays open. A paid request can still end up without a durable record if:
- GCS is unavailable for longer than the bounded retry budget
- the process is killed between response and write (task timeout, OOM, preemption)
- permissions or the bucket change mid-run
- a read-back fails permanently

**Proposed narrow mitigation for Step 022, not implemented:**
1. Generate the `attempt_id` before the provider call.
2. Run a GCS permission preflight (`testIamPermissions` for `storage.objects.create`/`get` on the exact bucket) before any paid request, as the GCS counterpart of the 018h guard.
3. Use `write_record` (idempotent, create-only) right after measurement, with a retry budget sized to the job timeout.
4. On a final failure, emit the canonical record to the job log as a bounded failure report and exit with a distinct non-zero code. The record contains no prompt, response or secret by construction. The record can then be recovered by replaying the same bytes through `write_record`, which is idempotent.
5. Never re-run the provider request.

## Cloud resources and paid calls

**None.** No `gcloud` command, bucket, IAM change, deployment, scheduler or provider request in Step 021. The local `gcloud` login from Step 020 was not used.

## Limitations

- The writer is offline-tested only; there is no live GCS proof yet.
- Not integrated with `run_attempt` or `real_benchmark`: cloud collection still requires the Step 020 Cloud SQL pattern.
- `REQUEST_FIELDS` is frozen for v1. A future storage column needs a v2 schema.
- Only Linux x86_64 wheels are pinned, as before.
- The bucket-metadata background GET adds one read per process. Its debug log line could include an exception string; it only logs at DEBUG level.
- 018f import is untested with exact values (see above).

## Design Q&A (concise)

- **Lead:** *Why is an identical replay a success while a different payload under the same name is an error, and how does create-only handle a lost acknowledgement?* Because the name is derived from the attempt's own id, so equal bytes are the same fact. Byte comparison after a 412 tells "our earlier write" from "someone else's". See `design-questions/021/lead-engineer.md`.
- **Principal:** *Where can a paid measurement still be lost, and what makes a record scientifically trustworthy?* In the response → write window. Provenance comes from the frozen schema, the canonical bytes, the exact SQL-row mapping and the stored price basis. See `principal-engineer.md`.
- **Senior manager:** *How do we roll this out safely?* Offline component first (this step), then one approved real object in Step 022 with the guard semantics preserved, then scheduling. See `senior-manager.md`.
- **Director:** *Is GCS worth it versus Cloud SQL?* GCS costs about $0.02–0.07/month against about $9.40/month for always-on SQL, with no per-run provisioning. The real cost driver becomes job runtime. See `director.md`.

## Next micro-step (one)

**Step 022:** explicitly approved, GCS-backed, OpenAI-only execution:
- Create a private records bucket and least-privilege IAM.
- Add a GCS fail-closed preflight before the paid call.
- Write the record with `write_record` after one paid run.
- Verify the real object independently.
- Scheduling comes later, in a separate step.

## MARKETING CHECKPOINT

**Not publishable yet.** n = 2 real measurements (018f, 020). Step 021 adds storage capability only, with no new measurements.
