# Step 019 — Disposable Docker-first local development and testing

**Status:** Pending implementation. This replaces the not-started 018i cloud pilot, which has been removed from GitHub main (recoverable from Git history). **One outcome:** an opt-in, one-command Docker workflow that builds, fully tests, serves, and cleanly tears down the local LLM Metrics stack without installing application dependencies or PostgreSQL on the host. Preserve existing native `./run.sh` for environments without Docker. Implement this step only, commit and STOP for ChatGPT review.

## Read first

Read `chatgpt-guidelines.md`, authoritative `prompts/PROMPT_WRITING_CONTRACT.md`, `CODING_GUIDELINES.md`, `prompts/DESIGN_QUESTIONS.md`, `design-questions/README.md`, `DECISIONS.md`, `PROJECT_STATUS.md`, the append-only `prompts/chatgpt-conversation.md`, `prompts/018h-output.md`, `prompts/018g-output.md`, `Dockerfile`, `.dockerignore`, `run.sh`, `requirements.txt`, `scripts/install_requirements.py`, `tests/test_postgres_integration.py`, relevant DB/migration tests, `llm_metrics/{config,storage,real_benchmark,web}.py`, and current deployment/build files. Inspect the latest commit `a20bf6f` (integration test database teardown) and its potential failure paths. Do not rewrite completed prompts or historical entries.

## Context / design choice

Developer machine currently has **no Docker**; Google Cloud Shell has Docker. Existing `./run.sh` creates a host `.venv`, runs unittest, seeds simulated data, executes a simulated measurement and starts the local dashboard. PostgreSQL integration tests require an explicitly configured `TEST_POSTGRES_URL`; previous testing left an orphaned host PostgreSQL database; Claude committed a new `tearDownClass` that attempts to drop the test DB.

User wants Docker-local artifacts and services to be **disposable**, so stopping/removing the Compose project leaves no application service or test database running on the host. Cloud Run production remains serverless and unchanged. Avoid a large cross-cutting rewrite of the existing native workflow: add a **Docker-first optional path**, with native `./run.sh` kept functional for machines without Docker.

## In-scope implementation

1. Add a small, understandable `compose.yaml` (or `docker-compose.yml`) with only necessary local services, preferably:
   - A PostgreSQL test service using an official version-compatible PostgreSQL image, ephemeral project-scoped named volume or tmpfs as appropriate, health check and loopback-only/no host port exposure unless essential.
   - A local application/test image built from a reviewed local Dockerfile stage or dedicated Docker test Dockerfile; it must include tests, scripts, migrations and required dependencies (production `.dockerignore` currently excludes tests and `run.sh`, so explicitly solve this). Do **not** bloat or accidentally change the existing production Cloud Run image's secret handling or default runtime.
   - No Redis, Nginx, MailHog, scheduler or extra services unless actual source code requires them today. No paid provider execution or external service calls during test.
2. Provide **simple documented commands** that operators can copy, ideally one shell wrapper such as `./docker-run.sh` with `test`, `up`, `down` (or clearly documented Compose commands):
   - `test`: build/start disposable PostgreSQL, wait until ready, run the full offline unittest suite **and the real PostgreSQL integration suite** with `TEST_POSTGRES_URL` pointing only to the Compose test database; exercise real Alembic migration, seeded simulated workflow and dashboard smoke test within containers as appropriate; exit nonzero on failure and **always** tear down containers/networks and disposable database volumes via trap/finally.
   - `up`: start a usable dashboard on configurable **127.0.0.1** local port, check HTTP readiness; clarify whether this mode intentionally preserves its volume until `down`.
   - `down`: tear down *only this project's* Compose resources including disposable volumes. Do not invoke global Docker prune, stop host PostgreSQL, delete unrelated Docker images/containers/volumes or alter systemd.
   - If a single `./docker-run.sh smoke` command is clearer than `test`+dashboard, choose the smallest ergonomic interface and document exact guarantees.
3. Keep tests deterministic and offline: no network to model-provider endpoints; no use of real API keys, `--real`, cloud secrets, or production databases. Pin/test meaningful Docker image versions, and prevent accidental use of user-supplied `TEST_POSTGRES_URL` against an outside database. Prefer explicit service DNS and a test database name. No host `.venv` or host PostgreSQL dependency for Docker path. Enforce non-root where feasible; do not hide root requirements of database initialization.
4. **Audit the latest test teardown fix carefully.** Dropping a database and terminating sessions is destructive; ensure the integration harness has fail-closed checks proving that the URL references the Compose test database/service and a deliberately disposable name, and that initialization/teardown cannot touch unrelated host/production DBs, even if the environment is inherited unexpectedly. Avoid unconditional termination of other sessions. If safe guard cannot be established, prefer Compose teardown owning the disposable whole DB instance and remove/limit test-level DROP DATABASE. Test teardown failure paths. Do not silently delete users' existing host test DBs or uninstall their host PostgreSQL.
5. Preserve **native `./run.sh`** as a first-class supported path (no Docker requirement), including its current simulated measurement/dashboard behavior and test-default safety. Add concise README/usage for choosing native vs Docker. If necessary make a minimal optional `run.sh` mode hook, but do not force every native developer into Compose or change `./run.sh` defaults.
6. **Clean artifact lifecycle:** project-specific container/network/volume disposal verified by `docker compose ps`/`volume ls` inspection; explain that image layers, Docker build cache and existing bind-mounted files are not removed automatically. Avoid a global cleanup promise. Any optional image cleanup must precisely target this project and not remove shared base images. Confirm that two clean, successive `test` runs work, leaving no residual running service/DB volume. For `up`, explicitly test `down`.
7. Prefer executing the Docker integration workflow in **Google Cloud Shell** (D070) if Docker is unavailable on the current machine, but do not provision GCP resources. If Cloud Shell cannot access the repo and run Docker or the environment cannot support privileged/daemon execution, truthfully mark Docker runtime verification blocked, implement static config/tests and **do not claim two real clean passes**. Do not install Docker on the user's laptop without asking.

## Acceptance checks

- Native `./run.sh` still works without Docker (test in available native environment and clearly disclose if dashboard cannot bind due to an occupied port).
- Docker `test` starts a fresh isolated PostgreSQL, runs real PostgreSQL integration against that service and the complete offline suite, performs schema/migration proof, and exits without paid requests; report actual test counts and skip counts.
- Dashboard smoke returns HTTP 200 from a localhost-bound, containerized local service; `up/down` lifecycle is clear.
- Docker `test` can run **twice from a clean state**, including failure-path cleanup. No orphaned project containers/networks/disposable DB volume afterward; nothing dependent on host PostgreSQL or `.venv`.
- No global Docker cleanup, unrelated service stop/disable, host DB/user destruction, cloud changes or hidden external API calls. Existing production Docker/Cloud Run behavior and 018h cloud-origin paid guard unchanged.
- Review `CODING_GUIDELINES.md`; no unused abstractions or unnecessary services.

## Out of scope, safety and cost

No GCP deployment, Cloud SQL, Cloud Build, Cloud Run changes, secrets, scheduler, paid OpenAI calls, other providers, public website, refactoring the existing storage backend, or changing measurement semantics. New local images/volumes may use local resources; do not mislabel local Docker as GCP spend. GCP goal remains under $10/day; existing budget alerts are not caps.

Preserve exact profile/workload, no fallback/routing/retries, measured TTFT/usage/price and request-ID provenance, real-vs-simulated separation, NULL-versus-zero facts, cache policy, migration integrity and atomic persistence. Keep raw prompts, outputs, keys, credentials and DB URLs with real secrets out of logs and commits.

## Completion artifacts and stop gate

Write `prompts/019-output.md` with exact commands, changed files and design choices, real Docker/runtime evidence vs static checks, both clean-run results, PostgreSQL migration/integration tests, native compatibility, teardown resource before/after list, limitations (images/cache/host files), security findings regarding `a20bf6f`, no cloud/paid-call confirmation, one proposed next step (return to controlled cloud pilot after Docker validation), and **MARKETING CHECKPOINT: not publishable yet**.

Create four distinct role-specific Q&A+critique files under `design-questions/019/{lead-engineer,principal-engineer,senior-manager,director}.md`, update `design-questions/README.md`. Update `PROJECT_STATUS.md` and `DECISIONS.md` as warranted, and append dated rationale/progress to `prompts/chatgpt-conversation.md` without altering prior history; explicitly record that the not-started 018i cloud prompt was superseded by Docker workflow Step 019. Run applicable focused tests, full offline suite, `./run.sh`, Docker integration and style checks; report truthful counts and limitations. Commit/push and **STOP for ChatGPT review**.

**Success:** optional Docker-first local workflow is repeatable, fully disposable for its own containers/networks/test DB volume, exercises genuine PostgreSQL tests, preserves the native workflow, and does not touch cloud billing or provider APIs.
