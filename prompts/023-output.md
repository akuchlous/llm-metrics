# Step 023 output — 15-minute OpenAI collection, bounded 24-hour pilot

## Status: PARTIAL

Implemented, deployed and activated. The 24-hour window was still running when this report was written. Status is PARTIAL only because the 96-slot results **have not been observed**. Every build, deployment, approval and first-run check is complete.

| | State |
|---|---|
| **Implemented** | `scheduled_collector` (atomic slot claims, 96-slot policy, late limit, clock check, expiry recheck, dry-run mode, structured events), `collector_audit`, GCS client additions, tests, staged cloud script, monitoring and lifecycle definitions |
| **Deployed** | dedicated Cloud Run Job `llm-metrics-collector` @ `sha256:5fb1a383d3f171baa11ba7042bda529cbe6b8281d2b63f9b1fb65ba16fa2ff4c`; Cloud Scheduler `llm-metrics-collector-15m`; 2 new service accounts; alerting |
| **Activated** | prod policy **2026-11-06T18:00:00Z → 2026-11-07T18:00:00Z** (96 slots), key reference attached to the collector job only, scheduler ENABLED |
| **Actually observed** | slot 18:00Z only: one claim, one paid request, one valid `prod` record, independently verified. Later slots were not observed here. |

| | |
|---|---|
| Source commit (built) | `1ce395c470f7fe9959fa8e20f43b1e3dbd8e4045` |
| Cloud Build | `13b90b82-5c1d-4498-a239-57142e25d811`, 31 s, SUCCESS, SA `llm-metrics-build@` |
| Image | `app:sha-1ce395c` @ `sha256:5fb1a383…2ff4c` |
| Approval A | "Approve A" in-session; first Phase A command at 2026-11-06T17:20:02Z. The alert email address akuchlous@gmail.com was named in the approved plan and not separately reconfirmed. |
| Approval B | "Approve B" in-session; activation at 17:47:38Z–17:48:11Z |
| User decision during Phase A | asked about a 1-minute test cadence; after the options were presented, the user chose **"Skip it"** |

---

## Implemented (Phase 0, offline)

**`llm_metrics/scheduled_collector.py`** (new; `python -m llm_metrics.scheduled_collector`, no arguments):
- **Fixed scope:** `targets.OPENAI` (`openai.gpt-6-luna.v1`), workload `interactive-chat-v1`, GCS backend, origin cloud `gcp`. Nothing is selectable by the caller.
- **Policy:** `LLM_METRICS_COLLECTOR_START` / `_EXPIRES` in the job env, UTC `YYYY-MM-DDTHH:MM:SSZ`. The start must be a quarter-hour boundary and the expiry exactly start + 24 h, which gives exactly `MAX_SLOTS = 96`. Missing, malformed, unaligned, shorter or longer policies are refused.
- **Sequence per invocation:**
  1. Configuration checks (no I/O).
  2. Slot = the current UTC quarter-hour, from the process clock.
  3. **Outside the window: a quiet no-op** (`policy_not_started` / `policy_expired`, exit 0, no I/O).
  4. Starting more than **7 minutes** after the slot began: `late_start`, exit 4.
  5. Prod mode: the key must be present.
  6. Step 022 storage preflight.
  7. **Claim**: create-only `…/v1/claims/<mode>/<profile>/<workload>/<cloud>-<region>/<date>/<HHMM>.json`, containing the slot, attempt id, claimed_at, scope and policy. Then read back. **The server's creation time must be within 120 s** of the local claim time.
  8. **Expiry and lateness are rechecked immediately before the request.**
  9. One request (`benchmark.measure_attempt`).
  10. One record (`object_results.write_record`) with the **claim's attempt id**.
- **Outcomes:**
  - A duplicate claim gives `duplicate_skip`, with no call.
  - A failed or ambiguous claim gives `claim_failed`, exit 4.
  - Clock skew, late start or expiry give exit 4.
  - A rejected request gives exit 2.
  - A record that can't be saved gives `not_persisted`, exit 3.
  - **A claimed slot is never retried.**
- **`dryrun` mode:** no provider; refused if any provider key is set. Claims go under `claims/dryrun/`; it also checks that a duplicate claim is refused, then writes a simulated-provider `test` record.
- **Events:** one sanitized JSON line per event, with `severity` read by Cloud Logging: `config_refused`, `policy_not_started`, `policy_expired`, `late_start`, `claim_failed`, `clock_skew`, `duplicate_skip`, `slot_claimed`, `expired_before_call`, `attempt_initiated`, `provider_rejected`, `recorded_success`, `recorded_failure`, `not_persisted`, `dryrun_duplicate_refused`. Never logged: the key, prompt, response, record payload or raw provider errors.

**`llm_metrics/collector_audit.py`** (new): read-only. It works from a local mirror (`--local`, after `gcloud storage cp`) or from GCS (`--bucket`). For every slot of the policy that has begun, it reports one of: recorded_success, recorded_failure, claim_without_record, or missing. It also lists records without a claim, invalid records and claims outside the policy. Exit 0 means clean, 1 means problems.

**Other changes:**
- `object_results.GcsObjectStore.created_time` / `list_names`.
- `real_benchmark._announce` renamed to `announce` (public, no behaviour change).

The one-off `real_benchmark` (SQL and GCS), `real_smoke`, `gcs_smoke`, the SQL guard, the Docker setup and `run.sh` are unchanged.

**Tests (`tests/test_scheduled_collector.py`, 22 new):**
- **Policy:** exactly 96 slots across midnight; invalid policies; slot arithmetic.
- **Refusals before any call:** 9 configuration cases, all before the store or provider; before-start and after-expiry no-ops; late start; claim failures (denied preflight, transient, lost acknowledgement, corrupt read-back); clock skew (which consumes the slot); expiry passing between claim and call.
- **Paid path:**
  - one claim, one call and one record, sharing the attempt id; sanitized output
  - duplicate deliveries make no call
  - **8 concurrent invocations make 1 call**
  - **every-minute deliveries over the full window plus 30 minutes on each side: exactly 96 calls** (672 duplicate skips, 672 late refusals, 30 + 30 no-ops)
  - a provider 503 is recorded with nulls
  - a 401 consumes the slot
  - a failed write gives exit 3 with no retry
  - a crash after the request is not retried, and the audit shows claim_without_record
- **Dry run:** never touches the provider; refuses with a key and after expiry.
- **Audit:** detects missing slots and claims without a record; the local-mirror CLI works; bad arguments are rejected.

**Results:**
- **Docker `./run.sh test`** (final tree): **533 tests, 5 skipped, 0 failures**. PostgreSQL integration executed (24 integration tests ok), dashboard HTTP 200, 0 containers and 0 volumes left. The 5 skips are the usual `test_container_config` ones.
  - The first run had 3 errors from a bad `sed` edit in my new test file (a `NameError`). I fixed it, and the second run was clean.
- **Production image smoke:** an expired policy is a no-op (exit 0); a 25 h policy is refused (exit 2); without credentials the claim fails (exit 4, no request); arguments are refused; the one-off SQL guard is unchanged.
- **Style:** pyink, isort and pylint are clean on new and changed code. The long lines and the protected-access warning already in `real_benchmark.py` are unchanged.

## Deployed (Phase A, Approval A, no key, no paid call)

| Stage | Time (UTC) | Result |
|---|---|---|
| `apis` | 17:20 | `cloudscheduler.googleapis.com` enabled |
| `accounts` | 17:20 | `llm-metrics-collector@` (runtime), `llm-metrics-scheduler@` (invoker) |
| `grants` | ~17:20 | Collector SA: `objectCreator` + `objectViewer` on `gs://llm-metrics-513617-results` only. **`llm-metrics-job@`'s `secretAccessor` on `OPENAI_API_KEY` removed**; the secret then had no accessors. The manual job keeps its bucket roles and stays credential-free. |
| `lifecycle` | ~17:21 | One rule: Delete if `age ≥ 7` **and** `matchesPrefix: ["attempts/v1/preflight/"]`. It covers only probes; claims, records and the backup bucket are unaffected. |
| `build` | 17:21:07 | Build `13b90b82…` → `sha256:5fb1a383…` |
| `create-job` | ~17:21 | `llm-metrics-collector`: digest above, SA collector, 1 task, 0 retries, 180 s, 1 vCPU / 512 Mi, command `python -m llm_metrics.scheduled_collector`, env GCS target plus `MODE=dryrun` and a dry policy 17:15Z–+24h. No secrets. |
| `scheduler` | 17:22:11–17:22:22 | `llm-metrics-collector-15m`: `*/15 * * * *`, `Etc/UTC`, POST `https://run.googleapis.com/v2/projects/llm-metrics-513617/locations/us-central1/jobs/llm-metrics-collector:run`, OAuth SA `llm-metrics-scheduler@`, retry count 0, attempt deadline 180 s. **Paused** about 11 s after creation; no delivery happened while it was briefly enabled. |
| `invoker` | 17:22:25 | `roles/run.invoker` (`run.jobs.run`, `run.routes.invoke`, `run.instances.invoke`; no `runWithOverrides`) for `llm-metrics-scheduler@` **on this job only** |
| `monitoring` | ~17:23 | Email channel `notificationChannels/11426004694589848451` (akuchlous@gmail.com). Log-based metric `llm_metrics_collector_events`. Policies: "error event or failed task" (ERROR on the collector job, enabled), "scheduler delivery failed" (enabled), "no collector event for 33 minutes (missed slots)" (absence, **disabled in A**). |
| `exec-dry` #1 | submitted 17:23:01 | `fxjv4`: **`late_start` (exit 4)**. The container started 9:54 into the 17:15 slot. The gate worked correctly, and this produced a real ERROR event. |
| `exec-dry` #2 | 17:33:47 → started 17:35:04 | `bphdj`, 17:30Z slot: `slot_claimed`, then `dryrun_duplicate_refused`, then `recorded_success`. Claim `attempts/v1/claims/dryrun/…/2026-11-06/1730.json`; record `attempts/v1/requests/test/2026-11-06/89f92bd17df24a3580dd48f1fdbe05d7.json`, sha256 `0bbb4869…5d08`. |
| `exec-expired` | 17:36:51 and 17:37:23 | `79bfj` and `6wlp6`: `policy_expired`, exit 0, no claim. **`79bfj` was not intended.** It was launched by a command the user interrupted; the first loop iteration had already started. It was harmless (dry-run, expired, no key). |
| `exec-alert` | 17:38:48 | `x9wvd`: `config_refused` (invalid mode), exit 2, ERROR |
| Independent check | ~17:41 | Operator download: the claim and record share attempt id `89f92bd1…`; the record is valid canonical v1 (`test`, provider `dummy`); the claim has metageneration 1 and GCS generation time 17:35:07.317Z against `claimed_at` 17:35:07.157Z (0.16 s); **no `claims/prod/` objects**. |
| `verify` | ~17:42 | Saved job, scheduler (PAUSED, `*/15`, `Etc/UTC`), invoker binding, bucket (UBLA, PAP enforced, lifecycle) and policies (two enabled, missed-run disabled) all as above |

**Alert visibility:** the ERROR log entries for `fxjv4` (`late_start`) and `x9wvd` (`config_refused`), plus Cloud Run's system ERROR for `fxjv4`, exist in Cloud Logging and match the enabled policy's filter. **Email delivery was not confirmed in-session**: no incident API was queried and the user has not confirmed receipt. The absence (missed-run) alert has not been exercised.

**Observed:** startup latency, from trigger to container start, was about 75–120 s. The scheduled 18:00 run started 2 min 1 s after the trigger, which leaves about 5 minutes of margin under the 7-minute late limit.

## Activated (Phase B, Approval B)

`activate 2026-11-06T18:00:00Z` ran at 17:47:38–17:48:11Z:
- `llm-metrics-collector@` was given `secretAccessor` on `OPENAI_API_KEY`. It is the only accessor.
- The job env was set to `MODE=prod`, `START=2026-11-06T18:00:00Z`, `EXPIRES=2026-11-07T18:00:00Z`.
- The secret reference `OPENAI_API_KEY:latest` was attached. The payload was never read.
- The missed-run policy was enabled.
- The scheduler was resumed (ENABLED, next 18:00Z).

Before activating I checked that no collector execution was running. Pricing was as verified in Step 022 ($0.10 / $0.50 / $0.01 cached per 1M), from the official page.

## Actually observed — first scheduled slot (18:00Z)

- **Scheduler:** delivered at 18:00:00.999Z, creating execution **`llm-metrics-collector-6dkbw`**. Container started 18:02:01Z; "completed successfully in 2m32.58s".
- **Events:** `slot_claimed` (attempt `f2a304348de94d86a4afdf4e76ed6271`), then `attempt_initiated`, then `recorded_success`. The announcement was printed and the log contains no key or payload.
- **Claim:** `attempts/v1/claims/prod/openai.gpt-6-luna.v1/interactive-chat-v1/gcp-us-central1/2026-11-06/1800.json`, `claimed_at` 18:02:38.066Z, same attempt id.
- **Record:** `attempts/v1/requests/prod/2026-11-06/f2a304348de94d86a4afdf4e76ed6271.json`. Downloaded with the operator identity: sha256 **`f9ab5581c337b875f928b81127f70394382f0661d91f20b2a259a3e220ca8323`**, matching the job log; `decode_record` is valid against the expected name.
- **Measurement:** success; TTFT 2087.4 ms; total latency 4940.5 ms; 107.8 tokens/s and 106.3 chunks/s; 1795 input / 0 cached / 300 output tokens (the cap); $0.0003295; provider request `req_064cf5f4170644009c41c2d09e27ef59`; recorded_at 18:02:43.254Z.
- **Audit** (`scripts/gcp/023_collector.sh audit 2026-11-06T18:00:00Z`, at 18:04:27Z): expected 1, claimed 1, `recorded_success: 1`, no problems, no records without a claim, no invalid records, no claims outside the policy.

**Not observed:** any slot after 18:00Z, the final count, any alert email, the missed-run alert, and the billed amount.

## Progress update — 2026-11-07T09:31Z (window still active; not final)

These are observed mid-window figures. The 96-slot result is still pending, with 33 slots left (09:45Z–17:45Z).

- **Audit at 09:30:45Z** (`scripts/gcp/023_collector.sh audit 2026-11-06T18:00:00Z`):
  - expected 63, claimed 62
  - `recorded_success` 61, `recorded_failure` 1
  - `missing` 1: the **09:30Z slot, which was still in progress**. The scheduler delivered it at 09:30:18Z, and the container had not yet started or claimed by 09:31:41Z. That is normal startup latency (about 2 min), not a missed slot. Its outcome will appear in the next audit. **Follow-up (observed from the job log):** slot 09:30Z was claimed at 09:32:12Z and recorded `recorded_success` at 09:32:16Z (attempt `261d46a552f743d384e4f7d87f05614b`). That makes **63 of 63** begun slots recorded, 62 of them successes.
  - claim_without_record 0, records without a claim 0, invalid records 0, claims outside the policy 0
- **Executions since 18:00Z:** 63; 62 succeeded, 0 failed, 1 running at audit time. The scheduler is ENABLED; next delivery 09:45Z.
- **Failures:** still only the 21:30Z `provider_error` (attempt `18e49063…`): nulls kept, no retry.
- **The 61 successful requests** (descriptive only, not statistics):

  | Metric | min | p50 | p90 | max | mean |
  |---|---|---|---|---|---|
  | TTFT (ms) | 929 | 1649 | 2265 | 12343 | 1928 |
  | Total latency (ms) | 3462 | 4293 | 5218 | 15236 | 4651 |
  | Output (tokens/s) | 77 | 115 | 132 | 136 | 114 |

  Input was always 1795 tokens with 0 cached; output ranged from 266 to 300 tokens. Derived model cost: **$0.020027**.
- **No events of these types so far:** duplicate skip, late start, claim failure, clock skew, not persisted.
- **Unchanged:** expiry 2026-11-07T18:00Z; the key reference is attached to `llm-metrics-collector` only; indefinite collection is not enabled.

## Progress update — 2026-11-07T05:14Z (window still active; not final)

These are observed mid-window figures. The 96-slot result is still pending.

- **Live counts at 05:14Z:**
  - 45 `prod` claims, so slots 18:00Z through 05:00Z are each claimed exactly once.
  - 45 window records in `requests/prod/` (46 objects including the Step 022 record).
  - 45 collector executions since 18:00Z, all succeeded, none failed.
- **Audit at 04:56Z** (`scripts/gcp/023_collector.sh audit 2026-11-06T18:00:00Z`, via a local mirror):
  - expected 44, claimed 44
  - `recorded_success` 43, `recorded_failure` 1, missing 0, claim_without_record 0
  - no records without a claim, no invalid records, no claims outside the policy
- **Event counts in Cloud Logging** (18:00Z–04:56Z): `slot_claimed` 44, `attempt_initiated` 44, `recorded_success` 43, `recorded_failure` 1. No `duplicate_skip`, `late_start`, `claim_failed`, `clock_skew` or `not_persisted` events. Scheduler ERROR entries: 0.
- **The one failure:** slot 21:30Z, attempt `18e49063ac444c70acc512da44d48c9c`, outcome `provider_error` after 15,226 ms. Stored with null tokens and cost and no provider request id; not retried.
- **The 43 successful requests** (descriptive only, not statistics):

  | Metric | min | p50 | p90 | max | mean |
  |---|---|---|---|---|---|
  | TTFT (ms) | 929 | 1685 | 2414 | 12343 | 2082 |
  | Total latency (ms) | 3594 | 4219 | 5218 | 15236 | 4724 |
  | Output (tokens/s) | 84 | 117 | 132 | 136 | 117 |

  Input was always 1795 tokens with 0 cached; output ranged from 266 to 300 tokens. Derived model cost: $0.014109.
- **Console figure explained:** the Cloud Console's Storage overview showed "1 bucket with objects, 3 objects, 429.33 B average". That is the daily-sampled storage metric, which still reflects the three 018f backup files ((162 + 543 + 583) / 3 = 429.33). It is not a live count.
- **Unchanged:** the window still expires 2026-11-07T18:00Z. The user started a request to make collection indefinite, then interrupted it; **no change was made**. Making collection indefinite would need a new reviewed step and approval, because the code deliberately refuses any policy that isn't exactly 24 hours.
- **Credentials:** the key reference is still attached to `llm-metrics-collector` only. Post-window actions are as above (`audit`, then `stop`).

## Pending: the rest of the 24-hour window

The authorization is **active and finite**: up to 96 slots from 18:00Z, with the last slot at 2026-11-07T17:45Z. After 18:00Z on 2026-11-07, every delivery is a `policy_expired` no-op, even if the scheduler is still running, because the code refuses independently.

**After 2026-11-07T18:00Z, the operator should run:**
```bash
cd ~/llm-metrics   # this repo
docker build -t llm-metrics-tool -f Dockerfile .        # same code as the digest
WORK_DIR=/tmp/023-audit TOOL_IMAGE=llm-metrics-tool \
  bash scripts/gcp/023_collector.sh audit 2026-11-06T18:00:00Z
bash scripts/gcp/023_collector.sh stop
```
- `audit` mirrors the claims and records, prints per-slot states (missing / claim_without_record / recorded_failure), and lists executions.
- `stop` pauses the scheduler, detaches the key reference, removes the collector account's access to the secret, and disables the missed-run alert.

**Credential state when this report was written:** the `OPENAI_API_KEY` reference **is attached to `llm-metrics-collector`**, and that job's account can read the secret. Nothing else is: the manual `llm-metrics-benchmark` job has no secret reference and its account has no secret access. The reference will **remain attached after expiry** until `stop` is run. Executions refuse after expiry, but the reference should still be removed.

**Emergency stop:** `bash scripts/gcp/023_collector.sh stop`. Detaching a reference does not revoke a key already injected into a running execution. Cancel one with `gcloud run jobs executions cancel <name> --project=llm-metrics-513617 --region=us-central1`, or rotate the key at OpenAI.

## Cost

| Item | Estimate per 24 h window (≤ 96 runs) |
|---|---|
| OpenAI `gpt-6-luna` | ≤ 96 × $0.0003295 ≈ **$0.032** |
| Cloud Run job (1 vCPU / 512 MiB, about 2–2.5 min per execution as observed) | ≤ about 14,400 vCPU-s, about $0.26 if not covered by the monthly free tier (240k vCPU-s per billing account) |
| GCS (about 4 Class A + 4 Class B operations per run, about 2 KB of objects) | about $0.002 |
| Cloud Scheduler | 1 job, within 3 free per billing account (otherwise $0.10/month; paused jobs count) |
| Logging / Monitoring | about $0; the alerting-policy price was not confirmed |
| **Total** | **≤ about $0.30/day worst case**; likely about $0.03–0.05 with the free tier |

Execution time (about 2.5 min) is longer than the 70 s assumed in Phase 0. It is mostly startup and Application Default Credentials / client setup. Phase A and the first slot cost well under $0.01. Billing lags, so nothing here is confirmed from billing. The budget alerts ($100/month) don't cap spending; the slot gate and the 24-hour policy are the request controls.

## Security and limitations

- The gate constrains **this code path**. Project owners can still update the job, delete claims (which re-opens slots), change IAM, or run other code with the key. The scheduler identity cannot do any of these.
- **Crash window:** a process killed after the paid response and before the record leaves a claim without a record, which the audit flags. It is not prevented.
- A burned slot (clock skew, a lost claim acknowledgement, a provider rejection) is not made up.
- Wall-clock dependence is mitigated by the GCS server-time check.
- Startup latency (up to 2 min observed) is the biggest threat to the 7-minute late limit under GCP congestion.
- 412 vs 403 for refused creates is still not observed (both are handled).
- Preflight probes are now deleted after 7 days by the prefix-scoped rule.
- The local `gcloud` is still logged in as project owner.

## Design Q&A (concise)

- **Lead:** *How does a create-only claim per slot prevent duplicate spend, and what becomes "refuse" instead of "retry"?* GCS's atomic create is the lock; everything ambiguous refuses and burns the slot. See `design-questions/023/lead-engineer.md`.
- **Principal:** *Where does the 96-call ceiling live, and what bypasses it?* In the code, in the job definition (the invoker can't override), and in credential scope. It doesn't stop project owners or total GCP spend. Next: an immutable policy object, a claims retention lock, a provider budget. See `principal-engineer.md`.
- **Senior manager:** *How was the move to unattended spend staged, and what's the handover?* Three phases, with surprises reported (late start, an unintended no-op run, the 1-minute request declined). The post-window audit and `stop` are operator actions. See `senior-manager.md`.
- **Director:** *Why 15 minutes straight away, and what must the pilot prove?* The same risk as hourly for 4× the data, at ≤ $0.30/day. Acceptance: ≥ 95% of slots recorded, every gap explained, zero duplicates, no expiry violations, billing matching the estimate. See `director.md`.

## Next recommendation (one)

After the window and the audit have been reviewed: **historical aggregation and static trend snapshots** from the immutable GCS records (D069). That means read-only aggregation over the 018f/020 backups plus the GCS records, latency and TTFT percentiles over the pilot window, and a versioned JSON/HTML snapshot, with no new paid collection until the data has been reviewed.

## MARKETING CHECKPOINT

**Not publishable yet.** One verified scheduled record so far (n = 4 real measurements overall). A single 24-hour, single-model, single-region window, even if complete, is not an adequate verified sample for public claims.
