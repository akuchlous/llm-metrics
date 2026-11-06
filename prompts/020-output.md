# Step 020 output — Guarded second OpenAI cloud pilot

## Status: COMPLETE — guard deployed and proven (A); one paid OpenAI measurement stored, independently backed up, and Cloud SQL torn down (B)

**Execution environment change:** after the Cloud Shell handoff (recorded at the end of this file for history) was written, the user installed `gcloud` 592.0.0 on the local machine and asked Claude to run the cloud phases from this session. Logged in as the project owner via `gcloud auth login`; every command passes `--project=llm-metrics-513617` (and `--region=us-central1` where regional). Cloud Shell was not used; D070 is amended accordingly (see `DECISIONS.md` D077).

**Approval A:** user replied "Approve A" in-session, recorded 2026-11-06T14:29:13Z (UTC of the first Phase A command), after the exact six-stage plan (`scripts/gcp/020_phase_a.sh`) and cost (~$0) were presented.
**Approval B:** user replied "Approve B" in-session, recorded 2026-11-06T14:38:36Z (UTC of the first Phase B command), after the nine-stage plan (`scripts/gcp/020_phase_b.sh`), resource settings, deletion/retention consequences and refreshed cost (< $0.05) were presented.

**Source commit / image:** application code `644870c` (validated) = `0ce36df` (built); Cloud Build `499c21cd-04f6-43ee-b2dc-efbf33c6223e`; image `us-central1-docker.pkg.dev/llm-metrics-513617/llm-metrics/app:sha-0ce36df` @ **`sha256:1b67b96f4186d08cd75abe8e870edc007c3241904a4d0a309afb96a32fe5a575`**.

**Paid provider requests in Step 020: exactly one** (`req_d382c49777f049e384ffdb38bda6c827`).

---

## Phase 0 — completed on the local development machine (2026-11-06)

Source commit validated: `644870cce591c5486088e060c3b84e01b30200b4` (application code; later commits add only scripts/docs).

### `./run.sh test` (real Docker Compose, Docker 29.9.3)

- **444 tests, 5 skipped, 0 failures.** Exit 0.
- PostgreSQL integration tests executed (not skipped) against the Compose `db` service.
- 5 skips: all `test_container_config.DockerfileDockerignoreConsistencyTest` (`Dockerfile and .dockerignore not present — skipped outside repo root`), because `Dockerfile.dev` does not copy the production Dockerfile into the image. They are not PostgreSQL skips.
- Dashboard smoke: HTTP 200. After exit: no `llm_metrics` containers or volumes remained.
- Note: run via `sg docker -c "./run.sh test"` because the shell predated the user's `docker` group membership; not a project issue.

### Production image offline check (`Dockerfile`, local build, not pushed)

Local image id `sha256:33fe8dba14e5…` (local only; Cloud Build will produce the deployable digest).

| Check | Result |
|---|---|
| Runtime user | uid 1000 (`appuser`), non-root |
| `/app` contents | `alembic.ini llm_metrics migrations requirements.txt scripts` — no `tests/`, `.git`, `.env*` |
| 018h guard present | `_check_cloud_db_url` in `/app/llm_metrics/real_benchmark.py` |
| `--network none`, origin `gcp`/`us-central1`, no DB URL, no key, `--provider openai --real --workload interactive-chat-v1` | exit **2**, `LLM_METRICS_DATABASE_URL is not set or is empty … require an explicit PostgreSQL … No request was made.` |
| origin `gcp`, `sqlite:///x.db`, dummy key | exit **2**, SQLite rejection, `No request was made.` |
| control: local origin, no key | exit 2, `OPENAI_API_KEY is not set. No request was made.` (guard does not affect local) |

The guard refusal precedes the API-key check (the gcp/no-key case never reaches the missing-key message).

### Pricing recheck (2026-11-06; official GCP pricing pages via search; verify live before Approval B)

| Item | Rate | This pilot |
|---|---|---|
| Cloud SQL `db-f1-micro` us-central1 (Enterprise, zonal) | ~$0.0105/h | ~2 h ≈ $0.02 |
| Cloud SQL SSD | ~$0.17/GB-month (10 GB min ≈ $0.0023/h) | ≈ $0.005 |
| Cloud Build e2-standard-2 default pool | $0.006/min; 2,500 free min/month per billing account | ~1–2 min, free tier |
| Cloud Run Jobs | $0.000018/vCPU-s, $0.000002/GiB-s | 2 executions < $0.001 |
| Secret Manager | $0.06/active version-month, **first 6 versions free**; 10k access ops free | $0 (earlier reports' ~$0.12/month overstated this) |
| OpenAI `gpt-6-luna` | $0.10 in / $0.50 out / $0.01 cached per 1M (third-party aggregators; unchanged vs `pricing.py`) | ≈ $0.0003 |
| **Total expected** | | **< $0.10** |

Orphan risk: a forgotten Cloud SQL instance ≈ $0.31/day (~$9.40/month), under the $10/day ceiling. The $100/month budget sends alerts only; it does not cap spend.

### Read-only GCP inventory

Initially blocked (no `gcloud` locally); run after the user installed `gcloud` — results in the next section. Script: `scripts/gcp/020_inventory.sh` (list/describe/get-iam-policy only, no secret payloads, explicit `--project`/`--region` on every command).

---

## Phase 0 read-only GCP inventory (2026-11-06, before 14:29Z, `scripts/gcp/020_inventory.sh`; its image-digest column was fixed afterwards — digest obtained with `--format='value(version,tags)'`)

- Project `llm-metrics-513617` (number 578834681009) ACTIVE, billing enabled; account `akuchlous@gmail.com`.
- **Job before Step 020:** image `us-central1-docker.pkg.dev/llm-metrics-513617/llm-metrics/app:sha-9cf8ac9` (digest `sha256:24c0a0b2558f8984efc7a8d77d99e364499c270eb8cf7dbe7e6879632cfbf7ac`, pre-guard); 1 task, maxRetries 0, timeout 180 s, SA `llm-metrics-job@`, 1 vCPU / 512 Mi, gen2; env `LLM_METRICS_ORIGIN_CLOUD=gcp`, `LLM_METRICS_ORIGIN_REGION=us-central1`, secret ref `OPENAI_API_KEY:latest`; no DB secret, Cloud SQL annotation empty; command `python -m llm_metrics.real_benchmark --provider openai --real` (no explicit workload). One past execution (`llm-metrics-benchmark-lz969`, 018f). No Cloud Run services.
- Cloud SQL: 0 instances. Cloud Scheduler API not enabled (no schedules).
- Secrets: only `OPENAI_API_KEY` (v2 enabled, v1 disabled); accessor only `llm-metrics-job@`.
- Backup bucket: US-CENTRAL1, versioning on, PAP enforced, UBLA on; `snapshots/018f/2026-11-04/` intact (3 objects, 1,288 B).
- Cloud Build: one prior build `2eb2f455…` (region us-central1, SA `llm-metrics-build@`, logging `CLOUD_LOGGING_ONLY`). Build SA: `artifactregistry.writer` on repo, `logging.logWriter` project, `storage.objectViewer` on `llm-metrics-513617_cloudbuild`. Job SA: `cloudsql.client` project. No SA-level IAM bindings on either SA.

## Phase A — guarded image deployment and negative proof (COMPLETE)

| Stage | Time (UTC) | Result |
|---|---|---|
| `remove-key` | 14:29:13 | `OPENAI_API_KEY` secret reference removed from the job (still on old image, not executed). Secret and versions untouched. Describe: env = origin literals only. |
| `build` | 14:29:42 | Cloud Build `499c21cd-04f6-43ee-b2dc-efbf33c6223e`, us-central1, SA `llm-metrics-build@`, `CLOUD_LOGGING_ONLY`, 30 s, SUCCESS, from clean `0ce36df63e77bfb6be7b57a80a170e54ac67ec08` (app code identical to validated `644870c`; `git diff` over `llm_metrics/ migrations/ Dockerfile requirements.txt alembic.ini .dockerignore scripts/install_requirements.py` empty). New file `cloudbuild.yaml` (D071). Image `app:sha-0ce36df`, **digest `sha256:1b67b96f4186d08cd75abe8e870edc007c3241904a4d0a309afb96a32fe5a575`**. |
| `deploy` | ~14:30 | Job updated by digest. |
| `verify` | ~14:30 | Saved spec: image `…/app@sha256:1b67b96f…a575`; SA `llm-metrics-job@`; taskCount 1; maxRetries 0; timeout 180 s; env only `LLM_METRICS_ORIGIN_CLOUD=gcp`, `LLM_METRICS_ORIGIN_REGION=us-central1`; **no secret refs**; cloudsql-instances `''`; command `python -m llm_metrics.real_benchmark --provider openai --real --workload interactive-chat-v1`. |
| `execute` (once) | 14:30:47 created, 14:31:47 completed | Execution `llm-metrics-benchmark-q9nlr`: failedCount 1, 0/1 tasks succeeded, `NonZeroExitCode` **exit code 2**, ran the new digest. No retry. |
| `logs` | — | `Container called exit(2).` and `Error: LLM_METRICS_ORIGIN_CLOUD='gcp': LLM_METRICS_DATABASE_URL is not set or is empty. Cloud-origin paid requests require an explicit PostgreSQL LLM_METRICS_DATABASE_URL to prevent data loss to ephemeral container storage. No request was made.` The only ERROR entry is the Cloud Run system audit event "0/1 tasks were a success". No key, URL or prompt in logs. |

**Negative-proof reasoning (observed vs inferred):** observed — the deployed digest printed the 018h guard message and exited 2; no `OPENAI_API_KEY` was attached, no DB existed. Inferred from code (`real_benchmark.run()` order) and the local image smoke — the guard returns before the key is read or an adapter is constructed, so no provider request could be made. Two independent barriers held: no credential and the guard. Zero paid provider attempts.

**Job after Phase A:** guarded digest, no credentials, no DB, idle. Old image `sha-9cf8ac9` retained in Artifact Registry (rollback reference only; never execute).
**Phase A cost:** Cloud Build 30 s (free tier), one ~1 min Cloud Run execution (< $0.001); a ~0.5 MB Cloud Build source tarball remains in `gs://llm-metrics-513617_cloudbuild/source/` (≈ $0).

## Phase B — one paid measurement, verified backup, teardown (COMPLETE)

Executed from the local machine with `SECRET_DIR`/`WORK_DIR` in the session scratchpad (outside the repo) and `TOOL_IMAGE=llm-metrics-prod-smoke:644870c` (local production build, application code identical to the deployed digest).

| Stage | Time (UTC) | Result |
|---|---|---|
| `preflight` | 14:38:36 | Scheduler API disabled; job taskCount 1, maxRetries 0, guarded digest; no running executions; 0 Cloud SQL instances. Model/profile/workload unchanged; `gpt-6-luna` rates unchanged vs `pricing.py` (third-party aggregators; OpenAI page not directly confirmed). |
| `create-sql` | 14:38:59 → 14:48:42 | `llm-metrics-pg-020`: POSTGRES_17 (server 17.11), ENTERPRISE, `db-f1-micro`, ZONAL `us-central1-c`, 10 GB SSD, no storage auto-increase, automated backups **off**, no final backup, no retained backups on delete, deletion protection off; public IPv4 with **zero authorized networks** (connector-only, 018f pattern). |
| `create-db` | ~14:49 | Database `llm_metrics`; user `llm_metrics_app` with a 64-hex random password generated into a 0600 file and passed to `gcloud` via `--flags-file` (never argv/history/stdout); secret `LLM_METRICS_DATABASE_URL` v1 created from stdin (Unix-socket URL `postgresql+psycopg2://…@/llm_metrics?host=/cloudsql/llm-metrics-513617:us-central1:llm-metrics-pg-020`); accessor binding only `llm-metrics-job@`. No new IAM roles (job SA already had project `cloudsql.client`). |
| `proxy-up` + `migrate` | 14:49:22 | Local `cloud-sql-proxy:2.14.1` container, OAuth token via `CSQL_PROXY_TOKEN` env (not argv). `storage.connect()` → Alembic head **`f1a2b3c4d5e6`**; tables `alembic_version`, `observations`, `requests`; **0 requests / 0 observations** before the paid call. |
| `attach` | ~14:50 | Job: Cloud SQL mount `llm-metrics-513617:us-central1:llm-metrics-pg-020`; secret refs `LLM_METRICS_DATABASE_URL:latest` and existing `OPENAI_API_KEY:latest` (v2; payload never read); guarded digest, `--real`, openai / `interactive-chat-v1`, 1 task, 0 retries, 180 s. |
| `execute` (once) | 14:50:11 submitted; task ran 14:50:20 → 14:51:40 | Execution **`llm-metrics-benchmark-4mwqz`: succeeded 1/1, exit 0**, "completed successfully in 1m19.41s". Not re-run. |
| `verify` | ~14:53 | See measurement table. Exactly 1 request and 4 observations in a database that did not exist before this step, so the 018f record cannot be counted. |
| `export` | 14:54:14–16 | `gs://llm-metrics-513617-pilot-backups/snapshots/020/2026-11-06-llm-metrics-benchmark-4mwqz/` (new prefix; script refuses an existing prefix; `--no-clobber`). |
| `check-backup` | ~14:54 | Independent re-download to a fresh directory: `sha256sum -c` OK ×3; CSV row counts {requests 1, observations 4} = manifest; CSV hashes = manifest; no key/Bearer/password/DB-URL patterns. 018f prefix unchanged (3 objects, 1,288 B). |
| `detach` | ~14:54:40 | Job: `OPENAI_API_KEY` and DB secret refs removed, Cloud SQL mount cleared; image still guarded digest. |
| `teardown` | 14:54:57 → 14:56:49 | Instance deleted; `gcloud sql instances list` 0; `gcloud sql backups list --instance=-` 0; secret `LLM_METRICS_DATABASE_URL` deleted; local credential dir, proxy container and network removed. |

Job log of the paid execution contained only the announcement, safe result summary and a **redacted** DB URL (`postgresql+psycopg2:///llm_metrics?host=/cloudsql/…`); no key, password, prompt or response.

### Second cloud measurement (observed values, read back from PostgreSQL before teardown)

| Field | Value | Note |
|---|---|---|
| Attempt id | `13caf417c6ba434fa378cc816f318379` | new; distinct from 018f `87428d1f…` |
| Provider request id | `req_d382c49777f049e384ffdb38bda6c827` | OpenAI `x-request-id` |
| Recorded at | 2026-11-06T14:51:34.612374Z | |
| Environment | `prod` | real, not simulated `test` |
| Provider / model / profile | openai / `gpt-6-luna` / `openai.gpt-6-luna.v1` | |
| Workload / cache policy | `interactive-chat-v1` / `disabled` | reasoning effort none (announced) |
| Origin | gcp / us-central1 | operator-declared; Cloud Run Job |
| Outcome | `success` | `failed_after_ms` NULL (not 0) |
| TTFT | 2469.9 ms | from just before `stream()` to first text item |
| Total latency | 5343.4 ms | until stream fully consumed |
| Output throughput | 105.3 tokens/s; 103.9 chunks/s | derived: first→last non-empty chunk, TTFT excluded |
| Tokens (provider-reported) | 1795 input, 0 cached, 300 output of max 300 | output hit the cap again |
| Rates stored | $0.10 in / $0.50 out / $0.01 cached per 1M | from `pricing.py`, verified 2026-11-01 |
| Cost (derived) | $0.0001795 + $0.00015 = **$0.0003295** | recomputed by hand: matches |
| Observations | 4: `total_latency`, `ttft`, `output_tokens_per_s`, `output_chunks_per_s` (ids 1–4, FK to the attempt) | |

**Unsupported facts:** the OpenAI invoice amount is not independently verified (cost is derived from stored rates and provider token counts). The TTFT/latency difference from 018f (2013→2470 ms, 4428→5343 ms) is two single samples and supports no claim.

### Backup (D072 layout, Step 020 prefix)

| Object | Bytes | SHA-256 |
|---|---|---|
| `requests.csv` (1 row, 23 cols) | 585 | `dae73fc7d303f7302b769810094bfc7385fe0efb3954ef9e573ea847f787ee5e` |
| `observations.csv` (4 rows, 8 cols, stable ids) | 547 | `aff07338365fe179907fdd4ab55a9cdff649dfce948b8959696f5d9c03452323` |
| `manifest.json` (step, run id, export time, schema v7, Alembic revision, server version, row counts, columns, CSV hashes, restore recipe, exclusions) | 1673 | `88e1b9b6a29ce01b715750b987ba9b2a756a24ecd84630d25858d30e0098be92` |
| `SHA256SUMS` | 242 | manifest of the three above |

**Restore — demonstrated, not just documented:** into a disposable local `postgres:17-alpine`: `storage.connect()` (Alembic head) → `\copy requests … CSV HEADER` → `\copy observations … CSV HEADER` → `setval(pg_get_serial_sequence('observations','id'), max(id))` → join returned `13caf417…|success|0.0003295|failed_after_ms IS NULL = t|4 observations|total_latency=5343.4,ttft=2469.9,output_tokens_per_s=105.3,output_chunks_per_s=103.9`. Empty CSV cells restore as NULL. Container removed afterwards.

```bash
mkdir -p ~/restore-020 && cd ~/restore-020
gcloud storage cp "gs://llm-metrics-513617-pilot-backups/snapshots/020/2026-11-06-llm-metrics-benchmark-4mwqz/*" .
sha256sum -c SHA256SUMS   # then follow manifest.json "restore"
```

---

## Job spec before / after Step 020

| Field | Before (inventory) | After Phase A | During B (attach) | Final (after detach) |
|---|---|---|---|---|
| Image | `app:sha-9cf8ac9` (pre-guard, tag) | `app@sha256:1b67b96f…` | same | same |
| `OPENAI_API_KEY` ref | `latest` | **removed** | `latest` (v2) | **removed** |
| `LLM_METRICS_DATABASE_URL` | absent | absent | secret `latest` | absent (secret deleted) |
| Cloud SQL mount | `''` | `''` | `…:llm-metrics-pg-020` | `''` |
| Command | `… --provider openai --real` | `… --provider openai --real --workload interactive-chat-v1` | same | same |
| Tasks / retries / timeout / SA | 1 / 0 / 180 s / `llm-metrics-job@` | unchanged | unchanged | unchanged |
| Executions | `lz969` (018f) | + `q9nlr` (exit 2) | + `4mwqz` (success) | 3 total |

## Remaining resources and cost

| Resource | State | Ongoing cost |
|---|---|---|
| Cloud Run Job `llm-metrics-benchmark` | guarded digest, no credentials, no DB, no schedule | $0 idle |
| Cloud SQL | none; no backups | $0 |
| Secret `OPENAI_API_KEY` | v2 enabled, v1 disabled (2 active versions) | $0 (first 6 versions free; earlier "$0.12/month" estimates were overstated) |
| Artifact Registry | `sha-0ce36df` (current) + `sha-9cf8ac9` (pre-guard, rollback reference only — never execute) | ~$0 (≈130 MB < 0.5 GB free) |
| Backup bucket | 018f (3 objects) + 020 (4 objects) ≈ 4.3 KB | ~$0 |
| Cloud Build bucket | one 540 KB source tarball from build `499c21cd` | ~$0 |
| Service accounts / budget | unchanged | $0 |
| Local machine | `gcloud` logged in as project owner; default project now `llm-metrics-513617` | — |

**Step 020 spend (estimated):** Cloud SQL ~18 min of `db-f1-micro` + 10 GB SSD ≈ $0.004; two Cloud Run Job executions (~2.5 min total of 1 vCPU/512 MiB) ≤ $0.003 and likely within free tier; Cloud Build 30 s within free tier; Secret Manager/GCS ≈ $0; OpenAI ≈ $0.00033. **Total < $0.01**, far below $10/day. Billing console not yet showing these charges; the figures are estimates.

## Tests

| Run | Result |
|---|---|
| `./run.sh test` (Docker Compose, before cloud work, `644870c`) | 444 tests, 5 skipped, 0 failures; PostgreSQL integration executed; HTTP 200; clean teardown |
| `./run.sh test` (Docker Compose, final tree with all Step 020 files) | 444 tests, 5 skipped (same container-config skips), 0 failures; PostgreSQL integration executed (24 integration-module tests ok); HTTP 200; 0 containers / 0 volumes left |
| Focused (host, repo root): `tests.test_container_config`, `tests.test_cloud_db_guard` | 36 tests OK, 0 skipped (the 5 container-config tests skipped inside Docker run here) |
| Production image smoke (local) | non-root, no tests/secrets, guard exit 2 ×2, local control path |
| `020_db_tool.py` against disposable local PG17 | migrate/verify/export OK; special-character password handled |
| Backup restore into disposable local PG17 | OK (above) |

No package code changed in Step 020 (only `scripts/gcp/`, `cloudbuild.yaml`, docs), so no new unit tests; the scripts were exercised against real PostgreSQL and the real cloud resources. `setup.sh` installation on other distributions and interactive Ctrl+C cleanup remain unproven (not in scope). Style tools (pyink/isort/pylint) not run on the new script.

## Changed files

| File | Change |
|---|---|
| `cloudbuild.yaml` | New: reproducible Cloud Build (least-privilege SA, `CLOUD_LOGGING_ONLY`, immutable tag) — D071 follow-up |
| `scripts/gcp/020_inventory.sh` | New: read-only inventory |
| `scripts/gcp/020_phase_a.sh` | New: staged Phase A (remove-key/build/deploy/verify/execute/logs) |
| `scripts/gcp/020_phase_b.sh` | New: staged Phase B (preflight → teardown) |
| `scripts/gcp/020_db_tool.py` | New: migrate/verify/export with manifest, run in the production image |
| `prompts/020-output.md`, `design-questions/020/*`, `design-questions/README.md`, `PROJECT_STATUS.md`, `DECISIONS.md`, `prompts/chatgpt-conversation.md` | Completion artifacts |

`scripts/` is excluded from the production image by `.dockerignore` (only `install_requirements.py` is allowed), so none of these scripts ship in the container.

## Limitations

- n = 2 real cloud measurements total (018f, 020), one provider, one region, one workload; both hit the 300-token output cap. No statistics.
- Origin is operator-declared; the guard is a configuration gate, not proof of durability.
- The per-pilot Cloud SQL pattern costs ~10 min of provisioning and manual steps per measurement; it is not a recurring design.
- The `OPENAI_API_KEY` payload validity is only proven indirectly (the request succeeded); its v1 is disabled, not destroyed.
- `gcloud` on the local machine is now authenticated as project owner (broad standing credential); consider `gcloud auth revoke` when not doing cloud work.
- Cost figures are estimates until the billing export shows them.

## Design Q&A (concise)

- **Lead:** *Why remove the key before deploying the guarded image, when the guard alone already blocks?* Two independent barriers: if the build had silently packaged old code (wrong SHA, cache) the run would still fail at "OPENAI_API_KEY is not set", spending nothing; the observed message then distinguishes "guard works" from "no key". See `design-questions/020/lead-engineer.md`.
- **Principal:** *Is "create Cloud SQL → one request → CSV export → delete" a viable storage pattern?* Proven safe for n=1 and ~$0.004/run, but ~10 min provisioning, manual steps and backups-as-CSV make it wrong for recurring collection; the next step should design a durable low-cost store. See `principal-engineer.md`.
- **Senior manager:** *How were approval and teardown risk controlled?* Two in-session gates, staged scripts with inspection between stages, teardown conditional on independent backup verification, explicit no-retry. See `senior-manager.md`.
- **Director:** *What did $0.01 buy?* A deployed fail-closed guard and a repeatable, auditable single-measurement path; it did not buy publishable data. See `director.md`.

## Next micro-step (one)

Design (analysis + decision, no provisioning) the smallest durable, low-cost **recurring OpenAI-only collector and export/static-snapshot pipeline** that avoids recreating Cloud SQL per measurement.

## History: original Cloud Shell handoff (superseded the same day; not used)

The user chose (2026-11-06) to execute cloud phases from a Claude Code session started inside Cloud Shell. That session must:

1. `cd ~/llm-metrics && git pull --ff-only`; read `prompts/020-guarded-second-openai-cloud-pilot.md` and this file.
2. Run `bash scripts/gcp/020_inventory.sh` and confirm the job still references `app:sha-9cf8ac9`, has `OPENAI_API_KEY:latest`, no DB secret, no Cloud SQL, no scheduler; 018f backup intact. Determine how the 018f Cloud Build was configured (region, logging) before writing the build command.
3. Present the exact Phase A commands and obtain **Approval A in that session**. Phase A order: build from the recorded SHA with `llm-metrics-build` SA → **remove the `OPENAI_API_KEY` reference first** → update the job by digest (1 task, 0 retries, bounded timeout, origin gcp/us-central1, explicit `--real` command, no DB) → verify spec → execute once → expect exit 2 + `No request was made`.
4. Only then request **Approval B** with refreshed prices, and follow Phase B exactly (one paid request, no retry, verified backup before teardown, remove key reference again).
5. Complete this file (status, approval records, digests, job spec before/after, evidence), design questions, `PROJECT_STATUS.md`, `DECISIONS.md`, conversation history; re-run `./run.sh test` if code changed; commit, push, STOP.

---

## MARKETING CHECKPOINT

**Not publishable yet.** n = 2 real cloud measurements (018f, 020) of one OpenAI model from one region; not a statistical sample, not a time series, and not a provider comparison.
