# Step 020 output — Guarded second OpenAI cloud pilot

## Status: IN PROGRESS — Phase A COMPLETE (guard deployed and proven); Phase B awaiting Approval B

**Execution environment change:** after the Cloud Shell handoff below was written, the user installed `gcloud` 592.0.0 on the local machine and asked Claude to run the cloud phases from this session. Logged in as the project owner via `gcloud auth login`; every command passes `--project=llm-metrics-513617` (and `--region=us-central1` where regional). The Cloud Shell handoff section is kept for history but was not used.

**Approval A:** user replied "Approve A" in-session, recorded 2026-11-06T14:29:13Z (UTC of the first Phase A command), after the exact six-stage plan (`scripts/gcp/020_phase_a.sh`) and cost (~$0) were presented.
**Approval B:** not yet granted.

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

Not run on the local machine (no `gcloud`; D070). Script committed: `scripts/gcp/020_inventory.sh` (list/describe/get-iam-policy only, no secret payloads, explicit `--project`/`--region` on every command).

---

## Phase 0 read-only GCP inventory (2026-11-06T14:2xZ, `scripts/gcp/020_inventory.sh`)

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

## Handoff to the Cloud Shell Claude Code session

The user chose (2026-11-06) to execute cloud phases from a Claude Code session started inside Cloud Shell. That session must:

1. `cd ~/llm-metrics && git pull --ff-only`; read `prompts/020-guarded-second-openai-cloud-pilot.md` and this file.
2. Run `bash scripts/gcp/020_inventory.sh` and confirm the job still references `app:sha-9cf8ac9`, has `OPENAI_API_KEY:latest`, no DB secret, no Cloud SQL, no scheduler; 018f backup intact. Determine how the 018f Cloud Build was configured (region, logging) before writing the build command.
3. Present the exact Phase A commands and obtain **Approval A in that session**. Phase A order: build from the recorded SHA with `llm-metrics-build` SA → **remove the `OPENAI_API_KEY` reference first** → update the job by digest (1 task, 0 retries, bounded timeout, origin gcp/us-central1, explicit `--real` command, no DB) → verify spec → execute once → expect exit 2 + `No request was made`.
4. Only then request **Approval B** with refreshed prices, and follow Phase B exactly (one paid request, no retry, verified backup before teardown, remove key reference again).
5. Complete this file (status, approval records, digests, job spec before/after, evidence), design questions, `PROJECT_STATUS.md`, `DECISIONS.md`, conversation history; re-run `./run.sh test` if code changed; commit, push, STOP.

---

## MARKETING CHECKPOINT

**Not publishable yet.** n = 1 real cloud measurement (018f); Step 020 has not yet produced a second one. Not a statistical sample or provider comparison.
