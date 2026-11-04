# Step 018e — Secure Cloud Run deployment readiness (code only)

**Status:** Pending. Execute this step only, commit, and stop for ChatGPT review.

## Goal and scope

Step 018d verified PostgreSQL 17 integration and database migration safety (13 integration tests; 376 tests total). The next product objective is **the first OpenAI measurement on Google Cloud**. Before provisioning cloud resources, this step must create a **minimal, secure, reproducible deployment artifact** for (a) a single-request Cloud Run Job and (b) a private read-only Cloud Run web/API service. No cloud deployment yet.

This is a focused security/deployability gate—not a general refactor or a new product. The following step, 018f, will address first cloud provisioning and deployment only after review.

## Required reading

Before implementation, read `chatgpt-guidelines.md`, `prompts/PROMPT_WRITING_CONTRACT.md`, `prompts/DESIGN_QUESTIONS.md`, `CODING_GUIDELINES.md`, `DECISIONS.md`, `PROJECT_STATUS.md`, `prompts/chatgpt-conversation.md`, `prompts/018d-output.md`, and relevant actual code/tests, especially `llm_metrics/web.py`, `real_benchmark.py`, `benchmark.py`, `storage.py`, `config.py`, `http_streaming.py`, `tests/test_postgres_integration.py`, `requirements.txt`, `scripts/install_requirements.py` and `run.sh`. Read the existing design-question format/index.

Start by briefly classifying discovered deployment risks into blocking and deferrable, and name the small set of files you will change.

## Required implementation

1. **Minimal production image:** add a small, deterministic `Dockerfile` and `.dockerignore`. Use a maintained Python/architecture pair compatible with all exact pinned wheel hashes; add hashes only for needed wheel platforms. The container must not include `.git`, `.env*`, credentials, local data/SQLite DBs, tests' secret configuration, or unrelated tooling. Run as a non-root user. Make sure no secrets are baked into layers or build args. Use a production WSGI server (e.g., Gunicorn with hash-pinned dependencies) for Flask, not Werkzeug. Bind the Cloud Run web process to `0.0.0.0:$PORT`; retain existing localhost-only behavior for local `./run.sh`.
2. **Clear runtime commands:** document/run two explicit container modes from the same image or minimal separate targets: (a) private web/API service, and (b) **single-shot** benchmark job whose explicit command selects exact OpenAI provider, versioned workload, and `--real` opt-in. The default image entrypoint must **never make paid calls**. No loops, scheduler, hidden retries or fallback. A one-shot job must terminate with meaningful exit status.
3. **Cloud access boundary:** web routes currently have no app-level auth. The deployment instructions/config must require Cloud Run authentication/IAM, deny unauthenticated access and avoid public ingress by default. Do **not** implement a speculative login system. Make clear Cloud Run IAM is the boundary; never claim local Flask itself enforces authentication. Separate read-only web identity from job identity with least-privilege guidance.
4. **Secrets, storage, and paid-call safety:** document use of Secret Manager / runtime injection rather than literal credentials in source, Dockerfile, `gcloud` command history, or committed files. Review any raw DB URL in engine-cache keys, error handling, reprs and debug output; eliminate meaningful leak paths with the least intrusive change. Avoid leaking credentials to SQLAlchemy/Alembic logs. Preflight database connectivity/schema readiness **before initiating the paid OpenAI request**, so a known-bad DB does not cause an orphaned billed attempt; add regression tests. A later write can still fail, and the output must acknowledge that limitation. Preserve existing one-attempt/no-retry behavior.
5. **Bounded execution:** document/implement appropriate total wall-clock ceiling for the job beyond the existing per-read socket timeout, and reasonable memory/CPU/concurrency settings; avoid invasive SSE redesign unless needed for a demonstrable blocker. Do not schedule any runs or introduce actual spend controls in this step; reserve recurring budget enforcement for a later reviewed step. Clearly document that cloud runtime timeout is an outer safety limit, not measurement timing.
6. **Destructive test guard:** `tests/test_postgres_integration.py` currently uses `DROP TABLE ... CASCADE` for its target DB and only checks localhost. Strengthen the opt-in harness to refuse unsafe database names or configurations and use a disposable test-only identity/schema; explicitly account for tunnels to production over localhost. Never run destructive tests against any real or shared DB. Tests must remain skipped normally. Minimize changes to the harness.
7. **Dependency and repo hygiene:** expand ignore rules for secret variants (`.env.*`, key/certificate files where appropriate) and container context. Audit pinned dependencies for security advisories using installed tooling/network if available; do not invent vulnerability findings or silently upgrade unrelated packages. Record scanner and actual findings, or explicitly report 'not scanned'. Prefer managed security controls instead of building custom auth or secret managers.

## Invariants and exclusions

Preserve v7 schema, NULL vs zero, atomic persistence, versioned workload and request-profile identity, authoritative usage, provider request ID, effective price basis, origin, cache facts, real vs simulated isolation, exact OpenAI profile, TTFT boundary and no retries/routing/fallback. No new database tables or provider integration. Do not make any real provider calls or create GCP resources. No Cloud SQL, Cloud Run, Artifact Registry, IAM or Secret Manager changes. **Google Cloud project `llm-metrics-513617` is the intended next-step project, not permission to provision.** Combined provider/API plus infrastructure budget target remains at or below $10/day; verify actual costs before 018f.

## Validation and outputs

- Full offline test suite, `./run.sh`, style checks, focused security/deployment tests. Build the Docker image and run a no-secret local container/web smoke test if Docker is available; prove non-root identity, absence of secret files and non-default paid execution. If Docker unavailable, mark the container build **unverified** and provide the exact commands for later verification.
- Show safe container commands and a **non-executed** private Cloud Run deployment checklist (IAM, service identities, Secret Manager, Cloud SQL connectivity, region, migration-before-traffic, timeouts, single-request execution, budget and teardown). Never include passwords or real API keys.
- Write `prompts/018e-output.md` with evidence/results and limits, changed files, remaining deployment blockers, test counts, Docker evidence, dependencies/advisories check, GCP/provider-spend confirmation, concise Design Q&A, **MARKETING CHECKPOINT** ('not publishable yet' unless credible data exists), commit SHA if available, and **one** smallest next step.
- Add four distinct, implementation-grounded role Q&A/critique files: `design-questions/018e/{lead-engineer,principal-engineer,senior-manager,director}.md`, following `prompts/DESIGN_QUESTIONS.md`; update index.
- Update `DECISIONS.md` and `PROJECT_STATUS.md` for changed truth. **Append only** a dated evolution entry to `prompts/chatgpt-conversation.md`; do not rewrite anything old.
- Commit and push, then **STOP**. Do not start 018f.

**Success:** A secure, verifiable container build and explicit one-shot job/private web runtime are ready for the first reviewed GCP deployment, with no cloud resources or paid model calls made.
