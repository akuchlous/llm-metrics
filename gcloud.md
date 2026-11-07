# Google Cloud guide — llm-metrics

A single, maintained map of everything this project runs on Google Cloud: what exists, why, who can do what, how data flows, and how to operate and stop it. Written for both humans and AI agents.

- **Last verified:** 2026-11-07T05:14Z (Step 023, pilot window active)
- **Source of truth:** the live project. This file describes it; re-verify with [§12 Verify the live state](#12-verify-the-live-state) before acting.
- **History of decisions:** `DECISIONS.md` (D068–D080). **Step evidence:** `prompts/0NN-output.md`.

> **Rules for anyone changing cloud resources (human or AI)**
> 1. Every billable or mutating change needs explicit approval **in the current session**. Prompts, past chats or the presence of credentials are not approval.
> 2. Pass `--project=llm-metrics-513617` (and `--region`/`--location=us-central1`) on every command. Never rely on the active gcloud config.
> 3. Never read, print or commit secret payloads (`OPENAI_API_KEY`, DB passwords). Metadata only.
> 4. Never retry a paid provider request. Never delete measurement records, claims or backups.
> 5. Update this file in the same commit as any cloud change (see [§14](#14-keeping-this-file-current)).

---

## 1. At a glance

| Item | Value |
|---|---|
| Project ID / number | `llm-metrics-513617` / `578834681009` |
| Region | `us-central1` (everything regional lives here) |
| Owner | `akuchlous@gmail.com` (`roles/owner`; the only human principal) |
| Billing | Linked billing account; budget **`llm-metrics-100usd`**: $100/month, email alerts at 50/90/100%. **Alerts do not cap spend.** |
| Cost target | ≤ $10/day total; current pilot ≤ about $0.30/day |
| Measured provider | OpenAI only: `gpt-6-luna`, profile `openai.gpt-6-luna.v1`, workload `interactive-chat-v1` |
| Results store | GCS bucket `llm-metrics-513617-results` (no database) |
| Scheduling | Cloud Scheduler `*/15 * * * *` UTC, bounded by a 24-hour policy in code |
| Databases | **None.** Cloud SQL was used only temporarily in Steps 018f and 020, and deleted. |
| Public endpoints | **None.** No Cloud Run services, no public buckets. |

---

## 2. Architecture

```text
 Cloud Scheduler                     Cloud Run Job                       Cloud Storage (private)
 llm-metrics-collector-15m   POST   llm-metrics-collector               gs://llm-metrics-513617-results
 */15 * * * * Etc/UTC  ───────────▶  python -m llm_metrics.             attempts/v1/
 retries: 0                  :run    scheduled_collector                  ├─ preflight/   probe (create/read/no-overwrite)
 as llm-metrics-scheduler@           as llm-metrics-collector@ ────────▶ ├─ claims/prod/ 1 lock per 15-min slot (before paying)
   (run.invoker on this job only)    1 task, 0 retries, 180 s            └─ requests/prod/ 1 immutable record per attempt
                                        │
                                        │ OPENAI_API_KEY (Secret Manager ref, latest)
                                        ▼
                                     api.openai.com /v1/responses  (one streamed request per claimed slot)

 Cloud Logging ── JSON events (severity) ──▶ Cloud Monitoring alert policies ──▶ email
 Manual one-off job: llm-metrics-benchmark (credential-free, idle)
 Builds: Cloud Build (llm-metrics-build@) ──▶ Artifact Registry llm-metrics/app:sha-<commit>
 Archive: gs://llm-metrics-513617-pilot-backups (018f, 020 CSV snapshots)
```

**One scheduled run, in order** (code: `llm_metrics/scheduled_collector.py`; decision D080):
1. Validate the fixed configuration and the policy (exactly 96 slots, 24 h). Outside the window: no-op, exit 0, no I/O.
2. Refuse if started more than 7 minutes after the slot began.
3. Storage preflight probe (`attempts/v1/preflight/`).
4. Create-only **claim** for this slot, read it back, and check GCS server time against the local clock (≤ 120 s). If the claim exists, skip; if the claim is ambiguous, refuse.
5. Recheck expiry. Then **one** OpenAI request.
6. Write **one** immutable record (same attempt id as the claim). If it can't be written: exit 3, no retry.

---

## 3. Inventory

### 3.1 Cloud Run Jobs (`us-central1`; no Cloud Run services)

| Job | Purpose | Image (by digest) | Identity | Config | Credentials |
|---|---|---|---|---|---|
| `llm-metrics-collector` | **Scheduled** 15-min OpenAI collector (Step 023) | `…/app@sha256:5fb1a383d3f171baa11ba7042bda529cbe6b8281d2b63f9b1fb65ba16fa2ff4c` (`sha-1ce395c`) | `llm-metrics-collector@` | 1 task, 0 retries, 180 s, 1 vCPU / 512 Mi; command `python -m llm_metrics.scheduled_collector` | `OPENAI_API_KEY:latest` **attached** during the active pilot |
| `llm-metrics-benchmark` | Manual one-off runs (Steps 018f–022) | `…/app@sha256:3da244acd8953fe522b36c256743a58ccc6ae80b343bc4e3925efb446de0b8a5` (`sha-ee33635`) | `llm-metrics-job@` | 1 task, 0 retries, 180 s; command `real_benchmark --provider openai --real --workload interactive-chat-v1` | **None.** Its SA also has no secret access, so it refuses at the key check before any I/O. |

**Collector environment** (literal env vars; the key comes from Secret Manager):

| Variable | Value | Meaning |
|---|---|---|
| `LLM_METRICS_ORIGIN_CLOUD` / `_REGION` | `gcp` / `us-central1` | Where measurements run from |
| `LLM_METRICS_RESULTS_BACKEND` | `gcs` | Explicit GCS backend (D079) |
| `LLM_METRICS_RESULTS_BUCKET` / `_PREFIX` | `llm-metrics-513617-results` / `attempts` | Results target |
| `LLM_METRICS_COLLECTOR_MODE` | `prod` (`dryrun` in tests) | Paid vs no-provider dry run |
| `LLM_METRICS_COLLECTOR_START` / `_EXPIRES` | `2026-11-06T18:00:00Z` / `2026-11-07T18:00:00Z` | The approved 96-slot window. The code rejects anything other than exactly 24 h. |
| `OPENAI_API_KEY` | secret ref `OPENAI_API_KEY:latest` | Removed by `stop` |

### 3.2 Cloud Scheduler (`us-central1`)

| Job | Schedule | Target | Auth | Retries | State |
|---|---|---|---|---|---|
| `llm-metrics-collector-15m` | `*/15 * * * *`, `Etc/UTC` | POST `https://run.googleapis.com/v2/projects/llm-metrics-513617/locations/us-central1/jobs/llm-metrics-collector:run`, deadline 180 s | OAuth as `llm-metrics-scheduler@` | **0** (a missed delivery is a missed slot) | **ENABLED** during the pilot; pause with `stop` |

### 3.3 Cloud Storage buckets

| Bucket | Location | Purpose | Protection |
|---|---|---|---|
| `llm-metrics-513617-results` | us-central1, Standard | **Live results**: records, claims, probes | Uniform bucket-level access, public access prevention **enforced**, soft delete 7 d, no versioning. Lifecycle: delete **only** `attempts/v1/preflight/` objects older than 7 days. |
| `llm-metrics-513617-pilot-backups` | us-central1, Standard | Read-only archive of the first two measurements | Uniform bucket-level access, public access prevention enforced, **versioning on** |
| `llm-metrics-513617_cloudbuild` | US multi-region | Cloud Build source tarballs (scratch) | Auto-created; safe to clean |

**Layout of `llm-metrics-513617-results`:**

```text
attempts/v1/
├── requests/prod/<YYYY-MM-DD>/<attempt_id>.json   # MEASUREMENTS. Immutable v1 record per paid attempt (D078)
├── requests/test/<YYYY-MM-DD>/<attempt_id>.json   # synthetic records from dry runs / storage smoke (simulated provider)
├── claims/prod/openai.gpt-6-luna.v1/interactive-chat-v1/gcp-us-central1/<YYYY-MM-DD>/<HHMM>.json
│                                                  # slot locks: one per UTC quarter-hour, written BEFORE paying
├── claims/dryrun/…                                # dry-run slot locks (no provider)
└── preflight/<YYYY-MM-DD>/<probe_id>.json         # 124-byte storage probes; auto-deleted after 7 days
```

**Layout of `llm-metrics-513617-pilot-backups`:**

```text
snapshots/018f/2026-11-04/            requests.csv, observations.csv, SHA256SUMS            (measurement #1)
snapshots/020/2026-11-06-llm-metrics-benchmark-4mwqz/
                                      requests.csv, observations.csv, manifest.json, SHA256SUMS (measurement #2)
```

### 3.4 Secret Manager

| Secret | Versions | Accessors | Used by |
|---|---|---|---|
| `OPENAI_API_KEY` | v2 **enabled** (`latest`), v1 disabled | `llm-metrics-collector@` only (during the pilot) | `llm-metrics-collector` job |

There is no database secret: `LLM_METRICS_DATABASE_URL` existed only during the Cloud SQL pilots and was deleted.

### 3.5 Artifact Registry (`us-central1`, repo `llm-metrics`, Docker)

| Tag | Digest | Source commit | Status |
|---|---|---|---|
| `sha-1ce395c` | `sha256:5fb1a383…2ff4c` | `1ce395c` (Step 023) | **In use** by `llm-metrics-collector` |
| `sha-ee33635` | `sha256:3da244ac…b8a5` | `ee33635` (Step 022) | In use by `llm-metrics-benchmark` |
| `sha-0ce36df` | `sha256:1b67b96f…a575` | `0ce36df` (Step 020) | Superseded |
| `sha-9cf8ac9` | `sha256:24c0a0b2…f7ac` | `9cf8ac9` (Step 018f) | **Pre-guard. Never execute.** Rollback reference only. |

Images are deployed **by digest**, never by tag. Each is built from a clean, pushed commit via `cloudbuild.yaml`.

### 3.6 Monitoring and logging

| Resource | Definition | Fires when | State |
|---|---|---|---|
| Alert: *llm-metrics collector: error event or failed task* | `scripts/gcp/023_monitoring/collector_errors.json` | any `severity>=ERROR` log on job `llm-metrics-collector` (config_refused, late_start, claim_failed, clock_skew, expired_before_call, provider_rejected, not_persisted, task failure) | enabled |
| Alert: *llm-metrics collector: scheduler delivery failed* | `scheduler_errors.json` | `severity>=ERROR` on scheduler job `llm-metrics-collector-15m` | enabled |
| Alert: *no collector event for 33 minutes (missed slots)* | `collector_missed_runs.json` | metric `llm_metrics_collector_events` absent for 1,980 s | enabled **only during an active window** |
| Log-based metric `llm_metrics_collector_events` | filter: collector job, `jsonPayload.component="llm-metrics-collector"` | counts all collector events | — |
| Notification channel | email `akuchlous@gmail.com` | — | — |

Collector log lines are JSON with `severity`, `component`, `event`, `slot`, `attempt_id`, `claim`, `record` and `sha256`. They never contain keys, prompts, responses or record payloads.

### 3.7 Enabled APIs that matter

`run`, `cloudscheduler`, `storage`, `secretmanager`, `artifactregistry`, `cloudbuild`, `logging`, `monitoring`, `billingbudgets`, `sqladmin` (no instances), `iam`.

---

## 4. Identities and permissions (least privilege)

| Principal | Role(s) | Scope | Why |
|---|---|---|---|
| `akuchlous@gmail.com` | `roles/owner` | project | Operator. The only identity allowed to approve and make changes. |
| `llm-metrics-collector@` | `storage.objectCreator`, `storage.objectViewer` | bucket `…-results` | Create and read probes, claims and records. **No delete or overwrite.** |
| | `secretmanager.secretAccessor` | secret `OPENAI_API_KEY` | The only key reader. Granted at activation, removed by `stop`. |
| `llm-metrics-scheduler@` | `run.invoker` (`run.jobs.run`, no `runWithOverrides`) | job `llm-metrics-collector` only | Can start the collector. Cannot change its env, arguments or policy. |
| `llm-metrics-job@` | `storage.objectCreator`, `storage.objectViewer` | bucket `…-results` | Manual one-off job (Step 022) |
| | `cloudsql.client` | project | Legacy from the Cloud SQL pilots. Harmless without instances; candidate for removal. |
| `llm-metrics-build@` | `artifactregistry.writer` | repo `llm-metrics` | Push built images |
| | `logging.logWriter` | project | Build logs (`CLOUD_LOGGING_ONLY`) |
| | `storage.objectViewer` | bucket `…_cloudbuild` | Read uploaded source |
| `578834681009-compute@` (default compute SA) | **none** | — | `roles/editor` was removed in 018g |

**Bypass surface (honest):** the 96-call gate limits *this code path*. Project owners can still update jobs, delete claims (which re-opens slots), change IAM or run other code with the key. Budgets alert but don't cap spending.

---

## 5. Data model (what is stored)

- **Record** (`requests/prod/…json`, schema `llm-metrics.attempt.v1`, D078): canonical JSON with `attempt_id`, `recorded_at` (UTC), `environment`, `request{…20 facts…}` and `observations[{metric,value}]`.
  - **Facts:** provider, model, request_profile_id, workload_id, origin, cache_policy, outcome, input, cached and output tokens, requested_max_output_tokens, prices per 1M, input/output/total cost, failed_after_ms, provider_request_id.
  - **Metrics:** `total_latency` (ms), `ttft` (ms), `output_tokens_per_s`, `output_chunks_per_s`.
  - **Unknown values are `null`, never 0.** Failed attempts have null tokens and costs and no observations.
  - Prompts, responses, headers and keys are never stored.
- **Claim** (`claims/prod/…/<HHMM>.json`, `llm-metrics.claim.v1`): `slot`, `attempt_id`, `claimed_at`, `mode`, `profile_id`, `workload_id`, `origin_*`, `policy{start,expires,max_slots}`. Its `attempt_id` equals the record's.
- **Probe** (`preflight/…json`, `llm-metrics.preflight.v1`): `probe_id` and `created_at` only.

---

## 6. Current pilot (Step 023)

| Item | Value |
|---|---|
| Window | **2026-11-06T18:00:00Z → 2026-11-07T18:00:00Z** (96 slots; last slot 17:45Z) |
| Approvals | Phase A "Approve A" (infrastructure, dry run); Phase B "Approve B" (activation 17:48Z) |
| Progress at 05:14Z | 45/45 begun slots claimed and recorded; audit at 04:56Z: 43 success, 1 `provider_error`, 0 missing |
| After expiry | Code no-ops every delivery, but the **scheduler stays enabled and the key stays attached until `stop` is run** |
| Indefinite collection | **Not enabled.** It would need a new reviewed step: the code accepts only exactly-24 h policies. |

---

## 7. Operating it (scripts in `scripts/gcp/`)

| Task | Command |
|---|---|
| Read-only inventory | `bash scripts/gcp/020_inventory.sh` |
| Audit a window (claims vs records) | `docker build -t llm-metrics-tool -f Dockerfile . && WORK_DIR=/tmp/audit TOOL_IMAGE=llm-metrics-tool bash scripts/gcp/023_collector.sh audit 2026-11-06T18:00:00Z` |
| See recent collector executions | `gcloud run jobs executions list --job=llm-metrics-collector --project=llm-metrics-513617 --region=us-central1 --limit=20` |
| Read collector events | `gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="llm-metrics-collector" AND jsonPayload.component="llm-metrics-collector"' --project=llm-metrics-513617 --freshness=1d --format='value(timestamp,severity,jsonPayload.event,jsonPayload.slot,jsonPayload.attempt_id)'` |
| List measurements | `gcloud storage ls -r gs://llm-metrics-513617-results/attempts/v1/requests/prod/ --project=llm-metrics-513617` |
| View one record | `gcloud storage cat gs://llm-metrics-513617-results/attempts/v1/requests/prod/<date>/<id>.json --project=llm-metrics-513617` |
| Download all records | `gcloud storage cp -r gs://llm-metrics-513617-results/attempts/v1/requests/prod ./records --project=llm-metrics-513617` |
| Staged collector setup / activation | `scripts/gcp/023_collector.sh` (stages `apis` … `activate <START>`; **each needs approval**) |
| Manual one-off GCS run (Step 022) | `scripts/gcp/022_gcs_pilot.sh` (needs approval) |

Console links (login required; nothing is public):
- Results bucket: https://console.cloud.google.com/storage/browser/llm-metrics-513617-results?project=llm-metrics-513617
- Cloud Run jobs: https://console.cloud.google.com/run/jobs?project=llm-metrics-513617
- Scheduler: https://console.cloud.google.com/cloudscheduler?project=llm-metrics-513617
- Alerting: https://console.cloud.google.com/monitoring/alerting?project=llm-metrics-513617

The Cloud Console's Storage "Total objects" overview is sampled daily and can lag up to about a day. Use `gcloud storage ls` for live counts.

---

## 8. Emergency stop / end of window

```bash
bash scripts/gcp/023_collector.sh stop
```
This:
- pauses the scheduler
- removes the `OPENAI_API_KEY` reference from `llm-metrics-collector`
- removes the collector SA's secret access
- disables the missed-run alert
- lists recent executions

An already-running execution keeps its injected key until it ends. Cancel it with `gcloud run jobs executions cancel <name> --project=llm-metrics-513617 --region=us-central1`, or rotate the key at OpenAI.

---

## 9. Costs (estimates; recheck official pricing before changes)

| Component | Basis | Estimate |
|---|---|---|
| OpenAI `gpt-6-luna` | $0.10 in / $0.50 out / $0.01 cached per 1M; about $0.00033 per attempt | ≤ $0.032/day at 96 runs |
| Cloud Run Jobs | about 2–2.5 min per execution (mostly startup), 1 vCPU / 512 MiB; monthly free tier 240k vCPU-s | $0 to about $0.26/day |
| Cloud Storage | about 1 KB per record; about 4 Class A + 4 Class B operations per run | about $0.002/day |
| Cloud Scheduler | 1 job; 3 free per billing account (paused jobs count) | $0 (else $0.10/month) |
| Secret Manager | 2 versions (first 6 free) | $0 |
| Artifact Registry | about 4 images, ≤ 0.5 GB free | about $0 |
| Logging / Monitoring | small volume; alert-policy pricing not confirmed | about $0 |
| **Standing cost when idle** | — | **about $0/month** (no database, no services) |

Billing lags by up to a day. Confirm in the Billing console.

---

## 10. Change history (cloud-affecting steps)

| Step | Date | Change |
|---|---|---|
| 018f | 2026-11-04 | APIs enabled; AR repo `llm-metrics`; SAs `llm-metrics-job@`, `llm-metrics-build@`; secret `OPENAI_API_KEY`; job `llm-metrics-benchmark`; temporary Cloud SQL (deleted); budget $100. Measurement #1. |
| 018g | 2026-11-04 | Removed `roles/editor` from the default compute SA; deleted DB secret; disabled key v1; created `…-pilot-backups` with the 018f snapshot. |
| 020 | 2026-11-06 | Guarded image `sha-0ce36df` by digest; negative proof; temporary Cloud SQL (deleted); 020 snapshot backup. Measurement #2. |
| 022 | 2026-11-06 | Bucket `…-results` (UBLA, PAP); `llm-metrics-job@` bucket roles; image `sha-ee33635`; storage smoke; first GCS record (#3); key detached. |
| 023 | 2026-11-06 | Scheduler API; SAs `llm-metrics-collector@`, `llm-metrics-scheduler@`; key access moved to the collector SA only; preflight lifecycle rule; job `llm-metrics-collector` (`sha-1ce395c`); scheduler `*/15`; alerts + metric + email channel; **24 h pilot activated 18:00Z**. |

---

## 11. Known gaps and follow-ups

- **Crash window:** a crash after a paid response but before the record write loses that measurement. The audit shows it as `claim_without_record`.
- **Startup latency:** about 2 min against a 7-minute late limit; GCP congestion could cause `late_start` refusals.
- **Not yet observed:** whether GCS returns 412 or 403 for a refused create (both are handled). The missed-run alert has not been fault-tested. Receipt of alert emails has not been confirmed.
- **Clean-up candidates:** `llm-metrics-job@` `cloudsql.client`; old images `sha-0ce36df`, `sha-9cf8ac9`; Cloud Build tarballs; key v1 (disabled, not destroyed).
- **No public delivery yet:** static snapshots are planned (D069).
- **Local credential:** a project-owner `gcloud` login exists on the developer machine. Revoke it with `gcloud auth revoke` when idle.

---

## 12. Verify the live state

```bash
P=--project=llm-metrics-513617; R=--region=us-central1
gcloud run jobs list $P $R
gcloud run jobs describe llm-metrics-collector $P $R --format='yaml(spec.template.spec.template.spec.containers[0].image,spec.template.spec.template.spec.containers[0].env)'
gcloud scheduler jobs describe llm-metrics-collector-15m $P --location=us-central1 --format='value(state,schedule,timeZone,scheduleTime)'
gcloud secrets get-iam-policy OPENAI_API_KEY $P
gcloud storage buckets describe gs://llm-metrics-513617-results $P --format='yaml(uniform_bucket_level_access,public_access_prevention,lifecycle_config)'
gcloud sql instances list $P            # expect: 0 items
gcloud monitoring policies list $P --format='table(displayName,enabled)'
```

---

## 13. Glossary

- **Slot:** a UTC quarter-hour (:00/:15/:30/:45). At most one paid request per slot.
- **Policy / window:** the approved activation interval in the job env; exactly 96 slots (24 h).
- **Claim:** an immutable create-only object that reserves a slot before any spend.
- **Record:** an immutable v1 JSON measurement of one attempt.
- **Preflight / probe:** a tiny object proving create, read and no-overwrite before spending.
- **Dry run:** a collector mode with no provider and no key; writes `claims/dryrun/` and `requests/test/`.
- **Exit codes:**
  - `0`: recorded, skip or no-op
  - `2`: config refused or provider rejected
  - `3`: paid but not persisted
  - `4`: refused after the slot check

---

## 14. Keeping this file current

When any cloud resource, IAM binding, schedule, image or policy changes:
1. Update the affected section(s), [§6](#6-current-pilot-step-023) and [§10](#10-change-history-cloud-affecting-steps), and the **Last verified** line at the top.
2. Re-run [§12](#12-verify-the-live-state) and correct anything that differs.
3. Commit the change together with the step's `prompts/0NN-output.md` and `DECISIONS.md` entry.
4. Never put secret values, signed URLs or personal tokens in this file.
