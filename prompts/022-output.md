# Step 022 output — Guarded first live OpenAI benchmark stored in GCS

## Status: COMPLETE

One real OpenAI `gpt-6-luna` measurement was executed from the Cloud Run Job and stored as one immutable v1 JSON object in a new private GCS bucket. There was no Cloud SQL and no database. The storage path was first proven with no provider credential (Phase A). The provider key reference was detached right after the single paid execution. No scheduler, no second provider, no retries.

| | |
|---|---|
| Source commit (built) | `ee336355247dc21f3b63791318b45da79c3cd59d` (Phase 0 code + tests + `scripts/gcp/022_gcs_pilot.sh`) |
| Cloud Build | `f6e6c017-2649-475e-a3e1-71a795d6e91f`, us-central1, SA `llm-metrics-build@`, 38 s, SUCCESS |
| Image | `us-central1-docker.pkg.dev/llm-metrics-513617/llm-metrics/app:sha-ee33635` @ **`sha256:3da244acd8953fe522b36c256743a58ccc6ae80b343bc4e3925efb446de0b8a5`** |
| Approval A | "Approve A", in-session; first Phase A command 2026-11-06T16:39:24Z |
| Approval B | "approved Step B", in-session; first Phase B command 2026-11-06T16:46:42Z |
| Paid provider requests | **exactly one** (`req_06166e6dcfa6427486b82cb7cd79d0e3`) |

---

## Phase 0 — code (offline), no cloud changes

| File | Change |
|---|---|
| `llm_metrics/config.py` | `LLM_METRICS_RESULTS_BACKEND`: `sql` (default when unset or empty) or `gcs`. Any other value raises `ConfigError` without echoing it. |
| `llm_metrics/benchmark.py` | `measure_attempt()` split from `run_attempt()`: the checks, one measurement and the pricing, unchanged. `run_attempt()` = `measure_attempt()` + `storage.save_request()`, so the SQL behaviour is identical. |
| `llm_metrics/real_benchmark.py` | Explicit GCS mode (`_run_gcs`). The SQL path and the 018h guard (`_check_cloud_db_url`) are unchanged; the announcement was only factored into `_announce()`. Exit code **3** = a request was made but its record is not confirmed durable. |
| `llm_metrics/object_results.py` | `preflight()`: a real create / read / refused-overwrite / unchanged probe under `<prefix>/v1/preflight/`. `PermissionDeniedError`. `GcsObjectStore.create` treats a 403 as "exists" **only if** the object is really there; otherwise the 403 is raised. |
| `llm_metrics/gcs_smoke.py` | **New.** Storage-only smoke with no provider. It refuses if any provider key is set, runs the preflight, writes a synthetic `test` record (simulated provider), checks that an identical replay is a no-op and a conflict is refused, then reads the record back. |
| `tests/test_gcs_mode.py` | **New**, 24 tests (below). |
| `tests/test_object_results.py` | The boundary test now asserts that `benchmark.py`, `storage.py` and `real_smoke.py` don't use records; `real_benchmark` does so intentionally, in GCS mode only. |
| `scripts/gcp/022_gcs_pilot.sh` | **New.** The staged cloud script used for Phases A and B. |

**GCS-mode order in `real_benchmark.run`:**
1. **Configuration checks** (no I/O):
   - origin, backend, price
   - GCS scope: origin cloud must be `gcp`, profile must be `openai.gpt-6-luna.v1`
   - explicit bucket/prefix (`target_from_environ`; `snapshots/` is reserved)
2. **API key** present.
3. **Storage preflight** (the only network access before the paid call): build the client, create the probe, read it, try an overwrite (must be refused), re-read. Any failure gives exit 2 and "No request was made", printing the error class only.
4. **Request:** build the adapter, allocate `attempt_id` and print it in the announcement, run `measure_attempt` (exactly one provider call).
5. **Write:** `build_record` with `recorded_at` set after the measurement, then `write_record` (create-only, read-back, bounded storage retries).
   - On `ResultStoreError`: exit 3. stderr names the attempt ID, outcome, error class and object name, and says "will not be retried". The record payload is never printed.
6. **Summary:** the object `gs://…` URI and the record SHA-256.

`real_smoke` and the local Docker / CLI paths are unchanged, since they use the default `sql` backend.

**Offline tests:**
- **Docker `./run.sh test`** on `ee33635`: **511 tests, 5 skipped, 0 failures**. The PostgreSQL integration tests ran (24 integration-module tests ok), the dashboard returned HTTP 200, and 0 containers and 0 volumes were left. The 5 skips are the same `test_container_config` ones as before. Counts: 487 + 24 new.
- **New `tests/test_gcs_mode.py` (24):**
  - **Refusals happen before the key, adapter or any I/O:** missing bucket/prefix; unsafe prefixes (not echoed); an invalid backend value; non-gcp origins; non-OpenAI targets; a missing key.
  - **SQL guard preserved:** backend unset or `sql`, GCS variables present without `gcs` mode, a `gs://` database URL, and a `sqlite` URL all hit the PostgreSQL guard.
  - **Preflight failures refuse with zero provider calls:** a denied create, a transient error, corrupt read-back, a store that allows overwrite, and a client that fails to construct (class name only).
  - **Preflight unit test.**
  - **Exactly one mocked paid call produces one complete `prod` record** with exact facts, and the announced ID equals the record ID and object name.
  - **Never printed or stored:** the key, the prompt, the response or the record payload.
  - **Failures:** a provider 503 gives a record with nulls; a 401 records nothing (exit 2); a failed write after the response gives **exit 3 with one provider call and no record**; a lost acknowledgement is reconciled; a racing conflicting object gives exit 3 and the existing object is untouched.
  - **`gcs_smoke`:** passes, and nothing lands in `prod`; refuses with any provider key or bad config; fails on storage faults; the CLI rejects extra arguments.
  - **403 handling:** a 403 on an existing object means "exists"; a 403 without an object means permission denied (sanitized).
  - **Backend config values.**
- **Focused run** (object_results, gcs_mode, cloud guard, DB preflight, openai_provider): 159 OK.
- **Production image smoke** (local build of the same tree):
  - SQL default with no database: exit 2 with the 018h message.
  - GCS mode without a bucket: exit 2.
  - GCS mode with a target but no credentials: exit 2, `preflight failed (DefaultCredentialsError)`, no request.
  - `gcs_smoke` with a key present: refused.
  - `gcs_smoke` without network: exit 1.
  - Runs as uid 1000.
- **Style:** pyink, isort and pylint are clean on new and changed code. The remaining long lines and the `_redact_db_url` protected-access warning in `real_benchmark.py` were already there and are unchanged.

## Phase A — real storage proof, no provider key (Approval A)

| Stage | Time (UTC) | Result |
|---|---|---|
| `bucket` | 16:39:24 | `gs://llm-metrics-513617-results` created: US-CENTRAL1, STANDARD, uniform bucket-level access **on**, public access prevention **enforced**, soft delete 7 days (default), no versioning, no retention policy. |
| `grant` | ~16:39 | Bucket-level only: `llm-metrics-job@` gets `roles/storage.objectCreator` and `roles/storage.objectViewer`; plus the default project legacy bindings. No project-level IAM change. |
| `build` | 16:40:00 | Build `f6e6c017…`, clean `ee33635` = origin/main, digest `sha256:3da244ac…`. |
| `deploy` / `verify` | ~16:40 | Job by digest. Env: origin gcp/us-central1, `RESULTS_BACKEND=gcs`, bucket, prefix `attempts`. Command `python -m llm_metrics.gcs_smoke`. **No secret references**, no Cloud SQL, 1 task, 0 retries, 180 s, SA `llm-metrics-job@`. |
| `execute` (once) | 16:41:09 → done | `llm-metrics-benchmark-dcvt4`: succeeded 1/1, exit 0, "completed successfully in 1m48.13s". |
| Job output | 16:43:07 | PASS preflight (`attempts/v1/preflight/2026-11-06/32c98081….json`); PASS create synthetic record `attempts/v1/requests/test/2026-11-06/0ceed501a44f4da99e599d02a4f96892.json`, sha256 `5c2712aa…e1f8`; PASS identical replay (nothing created); PASS conflict refused, original kept; PASS read back and validated. |
| Operator check | ~16:44 | Listing: 2 objects (124 B probe, 936 B test record). **`requests/prod/` empty.** Downloaded with the operator identity: `sha256sum` = `5c2712aa…` (matches the job log); `decode_record(expected_name=…)` gives valid canonical v1, `environment: test`, provider `dummy`, profile `dummy.dummy-model-v1.v1`, origin gcp/us-central1, 4 observations. Both objects: `metageneration 1`, single generation, `application/json`. |

**Observed vs inferred:**
- **Observed:** the job service account can create and read in the bucket; the overwrite and conflict attempts were refused and the originals are unchanged (one generation each).
- **Not observed:** whether GCS answered the refused creates with **412** or **403**. Both paths are handled and tested offline, and data-access audit logs aren't enabled.

## Phase B — one paid OpenAI attempt (Approval B)

| Stage | Time (UTC) | Result |
|---|---|---|
| Recheck | 16:46:42 | Last executions completed; no running task; 0 Cloud SQL instances; official pricing re-verified for this step ($0.10 / $0.50 / $0.01 cached per 1M, ≤272K tier, matches `pricing.py`); Phase A proof in hand. |
| `paid-config` | ~16:46 | Command `python -m llm_metrics.real_benchmark --provider openai --real --workload interactive-chat-v1`; GCS env unchanged; **only** the `OPENAI_API_KEY:latest` secret reference added (payload never read); no DB; 1 task, 0 retries, guarded digest. Spec verified. |
| `execute` (once) | 16:47:01 submitted; task 16:47:13 → 16:48:20 | **`llm-metrics-benchmark-fvv5b`: succeeded 1/1, exit 0** ("completed successfully in 1m7.46s"). Not re-run. |
| `detach` | 16:48:34 | `OPENAI_API_KEY` reference removed (verified: no `secretKeyRef` in the job). |

**Job log (sanitized, observed):** the announcement included `Attempt id: e00ee56c46ba499b8579ba3413611be3` and the preflight probe `attempts/v1/preflight/2026-11-06/fb9bb9f2….json`, printed before the request. Then the summary, then `Saved attempt e00ee56c… with 4 observations to gs://llm-metrics-513617-results/attempts/v1/requests/prod/2026-11-06/e00ee56c46ba499b8579ba3413611be3.json`, `Record sha256: 75e6986d… (created)`, and exit 0. The log has no key, prompt, response or record payload.

### Third cloud measurement: independently downloaded and validated

`gs://llm-metrics-513617-results/attempts/v1/requests/prod/2026-11-06/e00ee56c46ba499b8579ba3413611be3.json`: 952 bytes, `application/json`, metageneration 1. Downloaded with the operator identity:
- `sha256sum` = **`75e6986da593cec4325d552e5738ce516a966101c5f57b773b31ec699e3ba01b`**, equal to the job log.
- `decode_record(expected_name=…)` passed: canonical, schema `llm-metrics.attempt.v1`, and the name matches the content.
- No `sk-`, `Bearer`, `prompt`, `response` or `diagnostics` bytes.

| Field | Value (from the object) | Note |
|---|---|---|
| attempt_id | `e00ee56c46ba499b8579ba3413611be3` | allocated before the request; equals the announced id |
| recorded_at | 2026-11-06T16:48:15.090805Z | after the measurement |
| environment | `prod` | |
| provider / model / profile | openai / `gpt-6-luna` / `openai.gpt-6-luna.v1` | |
| workload / cache policy | `interactive-chat-v1` / `disabled` | reasoning effort none (announced) |
| origin | gcp / us-central1 | operator-declared |
| outcome | `success`; `failed_after_ms` null | |
| provider_request_id | `req_06166e6dcfa6427486b82cb7cd79d0e3` | |
| TTFT | 1913.42 ms | |
| total latency | 5314.04 ms | |
| output throughput | 88.32 tokens/s; 87.14 chunks/s | derived, TTFT excluded |
| tokens | 1795 input, 0 cached, 300 output of max 300 | provider-reported; output hit the cap |
| rates | $0.10 / $0.50 / cached $0.01 per 1M | |
| cost | $0.0001795 + $0.00015 = **$0.0003295** | recomputed: matches |
| observations | total_latency, ttft, output_tokens_per_s, output_chunks_per_s | |

**Not verified:** the OpenAI invoice amount (the cost is derived from provider token counts and stored rates). Comparing with 018f and 020 (TTFT 2013, 2470, 1913 ms) is three single samples and supports no claim.

## Final state and remaining resources

| Resource | State |
|---|---|
| Cloud Run Job `llm-metrics-benchmark` | digest `sha256:3da244ac…`; command `real_benchmark --provider openai --real --workload interactive-chat-v1`; env: origin and GCS target; **no secret references**; no Cloud SQL; 1 task, 0 retries, 180 s; no schedule. If executed, it refuses at "OPENAI_API_KEY is not set" before any storage or provider I/O. |
| Bucket `llm-metrics-513617-results` | private (UBLA + PAP); job SA has objectCreator + objectViewer on this bucket only. 4 objects, 2,136 B: 2 preflight probes, 1 `test` synthetic record, 1 `prod` record. |
| Backups `llm-metrics-513617-pilot-backups` | 018f (3 objects) and 020 (4 objects) unchanged. |
| Secrets | `OPENAI_API_KEY` only (v2 enabled, v1 disabled), not attached to the job. |
| Cloud SQL, database secrets, Scheduler | none. |
| Artifact Registry | `sha-ee33635` (current), `sha-0ce36df`, `sha-9cf8ac9` (pre-guard; never execute). |
| Cloud Build bucket | one more source tarball (~0.6 MB). |

**Step 022 spend (estimated; billing lags):**
- OpenAI: about $0.00033.
- Two Cloud Run executions of about 1.1–1.8 minutes at 1 vCPU / 512 MiB: under $0.003, likely within the free tier.
- Cloud Build: 38 s, free tier.
- GCS: a handful of operations and about 2 KB: about $0.

**Total under $0.01.** Ongoing about $0/month, and far below $10/day.

**Cost per scheduled attempt (for Step 023, estimate):** about 3 Class A operations (probe create, refused overwrite, record create) and 3 Class B (reads). At 96/day that's about 8,640 Class A a month (above the 5,000 free; about $0.02) plus about 1 KB per attempt. The Cloud Run job time of about 70–110 s per run dominates.

## Limitations and open risks

- **Crash window:** the paid-response-to-durable-write window is still open. If the container is killed or GCS stays unavailable after the response, a billed attempt is lost. It's identifiable only by the attempt ID printed before the request, and Cloud Logging is not a guaranteed backup. Exit 3 covers the case where the process survives.
- **Probe accumulation:** preflight probes accumulate (124 B each). A lifecycle rule for `attempts/v1/preflight/` hasn't been configured.
- **412 vs 403:** which one real GCS returned for the refused creates is unknown; both are handled.
- **Synthetic test record:** it lives in the same bucket under `requests/test/`. Analytics must filter on `environment`, which the path already separates.
- **Image size:** grew with the GCS dependency (Step 021). No image optimization in this step, as instructed.
- **Local credential:** `gcloud` is still logged in on the developer machine as project owner.
- **Statistics:** n = 3 real measurements in total (two in SQL backups, one in GCS). No statistics.

## Design Q&A (concise)

- **Lead:** *Why run a real create/read/no-overwrite probe instead of checking IAM, and why is the attempt ID allocated before the request?* IAM checks prove permissions, not that the bucket, network, credentials and precondition semantics all work end to end. A pre-assigned ID makes a billed-but-unstored attempt traceable. See `design-questions/022/lead-engineer.md`.
- **Principal:** *What still separates this from a trustworthy unattended collector?* The crash window, probe accumulation, missed-run detection, and no reconciliation against provider usage. See `principal-engineer.md`.
- **Senior manager:** *How did the two approvals contain risk?* Phase A proved storage with no key and wrote nothing under `prod`; Phase B attached only the key, ran once, and detached it immediately. See `senior-manager.md`.
- **Director:** *What does a GCS-backed run cost versus the Cloud SQL pilot?* About $0.0003 for the model plus under $0.003 of infrastructure, with no standing database. Job time is now the cost driver. See `director.md`.

## Next step (one, after review)

**Step 023:** cautious OpenAI-only scheduling, for example hourly at first:
- a Cloud Scheduler trigger for the existing job
- an explicit daily budget and cost monitoring
- missed-run and exit-3 detection with alerting
- a preflight-probe lifecycle rule
- a short, bounded validation period before any 15-minute cadence

## MARKETING CHECKPOINT

**Not publishable yet.** n = 3 real single measurements of one OpenAI model from one region; not a time series, not statistically meaningful, no provider comparison.
