# Step 020 output — Guarded second OpenAI cloud pilot

## Status: IN PROGRESS — Phase 0 local work complete; cloud phases handed off to a Claude Code session in Google Cloud Shell

No cloud resource has been changed and no paid provider call has been made at the time of writing.
Approval A: **not yet requested/granted.** Approval B: **not yet requested/granted.**
Approvals must be captured in the session that executes the cloud commands (the Cloud Shell session); nothing in this file is an approval.

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
