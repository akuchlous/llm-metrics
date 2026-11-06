# Step 018h — Fail-closed paid cloud execution and durable-store decision

**Status:** Pending. Implement exactly this small step, commit, and stop for ChatGPT review.

## Context and one objective

Step 018g is complete: all five cleanup findings resolved; one real OpenAI pilot request and four observations were backed up as private CSVs under `gs://llm-metrics-513617-pilot-backups/snapshots/018f/2026-11-04/`. Cloud SQL was deleted. The existing, currently idle Cloud Run Job `llm-metrics-benchmark` in `llm-metrics-513617` has `LLM_METRICS_ORIGIN_CLOUD=gcp` and no `LLM_METRICS_DATABASE_URL` because the stale secret was removed. **Current bug:** `config.get_database_url()` falls back to SQLite, so a manually invoked paid job could succeed while its measurements disappear with the ephemeral container.

**Objective:** Make the **paid benchmark command fail closed** if a cloud-origin run has no explicitly configured, durable-enough database destination; then provide a **small evidence-backed storage architecture decision** for inexpensive recurring OpenAI metrics. **No new storage backend or scheduled runs in 018h.**

## Read before coding

Read `chatgpt-guidelines.md`, `prompts/PROMPT_WRITING_CONTRACT.md` (authoritative), `prompts/DESIGN_QUESTIONS.md`, `design-questions/README.md`, `CODING_GUIDELINES.md`, `DECISIONS.md`, `PROJECT_STATUS.md`, append-only `prompts/chatgpt-conversation.md`, `prompts/018g-post-pilot-cleanup-and-backup.md`, `prompts/018g-output.md`, previous 018f report, and actual `llm_metrics/{config,real_benchmark,benchmark,storage,real_smoke,targets,workloads}.py`, `tests/test_preflight_db_check.py`, existing configuration tests, `Dockerfile`, and deployment configuration if present.

## Implementation scope — guard only

1. In the **real/paid execution boundary** (prefer `real_benchmark.run()`, which is shared with `real_smoke`), add a clear validation *before constructing provider adapters or making network/API requests*:
   - If `config.get_origin()` identifies a **non-local** origin, a real attempt **must** have an explicitly provided `LLM_METRICS_DATABASE_URL` with an approved, externally durable scheme for the current application (**PostgreSQL**). Reject missing/empty values, SQLite URLs (including absolute paths, `:memory:` and file locations), malformed or unsupported URLs, and configuration errors; do not allow fallback to `LLM_METRICS_DB_PATH`.
   - Local origin retains existing intentionally local SQLite behavior and local development commands. Do **not** globally forbid SQLite or change `get_database_url()` default for dashboards/simulated tests.
   - This guard is a configuration safety gate, **not proof of actual durability**. Existing `storage.connect()` preflight should still verify connection/schema before the paid request. Never print database credentials or full URLs. Use a sanitized, actionable refusal, exit code 2, and `No request was made`; do not silently choose another storage backend.
   - Do not overfit to GCP environment variable names or use a provider-specific hack. Preserve explicit origin semantics; document that operator-declared origins are not attestation of actual hosting. Avoid speculative framework abstractions.
2. Add real **offline regression tests** against the actual shared paid entry point (not copies of guard logic) proving:
   - GCP origin + no URL refuses before provider creation/network, **even when a fake API key is present**.
   - GCP origin + explicit SQLite URL refuses before provider/network (cover a file path and memory form).
   - Other non-local origin + missing URL refuses.
   - Local origin + normal SQLite path is still accepted and the previous local flow behavior is preserved (mock provider/network rather than make a paid request).
   - Cloud origin + explicit PostgreSQL URL passes validation to the existing DB preflight, and unreachable/bad DB aborts before a paid request.
   - No credentials in stdout/stderr/debug messages; no secrets in test fixtures or GitHub.
   - `real_smoke` delegation, exact one-attempt/no-retry contract and existing tests remain intact.
3. **Operational caveat:** the old deployed image `app:sha-9cf8ac9` remains vulnerable until a newer image is built and deployed. Document this clearly and **do not execute the existing Cloud Run Job**. Do not claim live cloud is protected by a local code commit. Provide nonexecuted, safe steps for a *later approved* job image update and verification; **do not** rebuild/push/deploy or change secrets/IAM in this step.

## Small durable-storage decision (analysis only, no implementation)

Evaluate **only** practical ways to preserve many small benchmark records for the next OpenAI-only pilot:
- A continuously provisioned Cloud SQL PostgreSQL instance (existing application schema unchanged).
- A Cloud Storage object-based, append-only results store with a compact export/publish step; explicitly assess required storage interface change, deduplication, atomicity, retries, concurrent writes, historical analysis, and backup/restore.
- An on-demand or serverless SQL alternative *only if* genuinely usable with the existing SQLAlchemy/PostgreSQL interface; name a concrete viable option, or state none clearly confirmed.

For each compare estimated **idle monthly cost**, per-run/operational cost, implementation complexity, data durability, migration/queries/analytics impacts, and cloud-job security. Verify current official pricing if internet is available; show region/config/assumptions and sources, not invented precision. Distinguish what is *already proven* (PostgreSQL pilot) from a hypothetical object-storage design. State whether the existing private 018f backup can be imported and what is not preserved by CSV. Provide **one recommended smallest next step**, not an implementation of all three.

Remember the locked product direction: one complete OpenAI-only collection → historical metrics → **static public HTML and versioned JSON** behind CDN (D069), with future Router/Xchange consuming cached snapshots. A public Flask server is not required. Prefer minimal idle cost and bot-safe publishing, but never sacrifice measurement correctness or durable writes.

## Safety, scope and invariants

**Offline only:** no paid OpenAI/provider calls; no Cloud SQL, GCS, Artifact Registry, Cloud Build, Cloud Scheduler or Cloud Run creation/change/execution; do not enable APIs, change IAM, upload secrets or touch billing. Reading public pricing pages is fine; live GCP read-only inspection only if already authorized and convenient. Project `llm-metrics-513617` is context, not provisioning permission. Long-run goal is **< $10/day** API plus infrastructure, substantially lower preferred; the existing $100/month billing budget is alert-only, not a hard cap.

Preserve versioned workload, request profile and exact provider/model identity, no retries/routing/fallback, TTFT timing, provider usage and request IDs, nullable unknown vs zero, caching/pricing provenance, atomic persistence and real/simulated separation. No schema changes, new providers, scheduling, or dashboard rewrite. No raw prompts, responses, keys or sensitive provider errors in persisted output or logs.

## Tests and deliverables

Run focused new regression tests, full offline unittest suite, `./run.sh`, and applicable code style checks from `CODING_GUIDELINES.md`. State actual counts and skips, and any inaccessible test environment, without claiming unrun tests passed.

Create `prompts/018h-output.md` containing code changes, exact guard decision table, test evidence, limitations (including old cloud image still unsafe), storage-options comparison with sources and costs, spend/resources confirmation, a concise Design Q&A, **MARKETING CHECKPOINT: not publishable yet**, and **exactly one** recommended next micro-step.

Create four distinctly role-specific questions with actual step-grounded answer and critique under `design-questions/018h/{lead-engineer,principal-engineer,senior-manager,director}.md`; follow `prompts/DESIGN_QUESTIONS.md` and update `design-questions/README.md`. Update `PROJECT_STATUS.md` and `DECISIONS.md` only for decisions/actions actually made. **Append** a dated explanation to `prompts/chatgpt-conversation.md` without altering earlier history or modifying previous numbered prompts.

Commit and push, then **STOP for ChatGPT review**. Do not begin 018i or deploy any container.

**Success:** A locally tested refusal path makes cloud-origin paid benchmark attempts impossible without explicit PostgreSQL configuration, local SQLite behavior is unchanged, and we have a grounded low-cost durable-storage decision to implement next—without cloud modifications or paid requests.
