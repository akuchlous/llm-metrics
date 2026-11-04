# Step 018g — Post-pilot security cleanup and durable backup

## Objective

Resolve the five outstanding findings from the successful 018f cloud pilot and preserve its first measurement durably. **This is a cleanup/backup step, not a scheduling or multi-provider step.** Work in Google Cloud Shell using project `llm-metrics-513617`; GitHub main remains canonical.

## Read first

Read `chatgpt-guidelines.md`, `prompts/PROMPT_WRITING_CONTRACT.md`, `prompts/DESIGN_QUESTIONS.md`, `design-questions/README.md`, `CODING_GUIDELINES.md`, `DECISIONS.md`, `PROJECT_STATUS.md`, `prompts/chatgpt-conversation.md`, `prompts/018f-first-openai-cloud-measurement.md`, `prompts/018f-output.md`, and relevant actual code and cloud configuration. Do not rewrite completed prompts or historical entries.

## Evidence

018f executed one successful OpenAI `gpt-6-luna` `interactive-chat-v1` Cloud Run Job, saved one request and four observations to PostgreSQL, exported them to `~/llm-metrics-018f-result/requests.csv` and `observations.csv` in Cloud Shell, and deleted Cloud SQL. The 018f output describes remaining IAM, secret, backup and temporary build-object issues.

## Phase A: inspect and request approval

Use read-only checks to verify **current** IAM and service-account dependencies, Cloud Run Job's secret references, secret version metadata (not values), Cloud Build artifacts, billing, and the existence and integrity of the exported CSVs. Determine whether the job is safely dormant given its deleted database.

Present a concise plan of exact intended resource changes, security implications, backup location, incremental cost, and recovery/rollback implications. **Stop for explicit in-session approval before any cloud mutation**, including IAM changes, secret version changes, Cloud Storage provisioning/upload and build-object deletion. If not approved, create a report clearly marked BLOCKED PENDING APPROVAL, commit, and stop. Never infer permission from being asked to execute this prompt.

## Phase B: five mandatory findings

1. **HIGH — default compute service account Editor access.** Inspect actual active dependencies, including Cloud Run and Cloud Build identities. Following specific approval, remove only unnecessary project-level `roles/editor` from the default compute service account. Keep narrowly scoped job/build permissions intact. Verify IAM again. If removal is unsafe, explain and stop rather than breaking existing jobs.
2. **MEDIUM — stale database URL secret.** Confirm the Cloud SQL instance was deleted and inspect consumers/config references without accessing credential values. Following approval, safely remove obsolete job references as needed, and delete the obsolete `LLM_METRICS_DATABASE_URL` secret only when safe. Record how the job can be configured again for future runs. Do not create another DB.
3. **MEDIUM — duplicate OpenAI secret versions.** Inspect version numbers/states and exact job version reference, without retrieving or comparing secret payloads. Only with approval, retire redundant version 1 **if version 2 is valid and retained and no workload pins version 1**. Do not break the job or expose/rotate the surviving key. Verify the final state.
4. **MEDIUM — pilot data only in Cloud Shell.** Verify the CSV contains one pilot request and four observation rows, check schema and no raw prompt/response/secrets, calculate SHA-256 digests, and propose a private, low-cost Cloud Storage backup. With approval, upload safely, verify by independent download and matching digests, and record private paths, sizes, UTC metadata, row counts, checksums and restoration instructions. Do not commit the CSVs or place them in a public bucket. Explain that this is a snapshot, not a full PostgreSQL backup or recurring storage design.
5. **LOW — orphaned Cloud Build source archives.** Inspect actual bucket objects and whether any active build references them. After approval, delete only verified orphaned source tarballs; preserve container images, logs and reusable build artifacts. Verify what remains.

Also recommend removal of the overbroad `Bash(gcloud *)` Claude setting if still present; do not silently change the operator's authorization settings.

## Safety and scope

No new Cloud SQL, scheduled benchmark, paid OpenAI request, public web service, public snapshot publisher, additional provider, routing or database refactor. No secret values, credential-bearing URLs, raw provider prompts/responses or sensitive logs in output or GitHub. Budget target is under $10/day including API and infrastructure; actual new storage costs must be checked before approval. Don't equate budget alerts with spend caps. Keep exact request profile, workload, origin, pricing, nullable unknowns and real-versus-simulated provenance. One pilot sample is not publishable.

## Validation and deliverables

For **each of five findings**, report baseline, dependency evidence, user approval, action taken, independent verification, and whether resolved/deferred/blocked. Do not claim cloud operations happened without evidence. Run focused tests if any code changes; full offline suite and `./run.sh` when applicable, distinguishing executed from inherited results.

Create `prompts/018g-output.md` with the five-item matrix, verified private backup/restore details, resource inventory, ongoing cost, exact approval boundary, test evidence, limits, concise Design Q&A, one proposed next step, and **MARKETING CHECKPOINT: not publishable yet**. Create four distinct, implementation-grounded role-specific Q&A + critiques under `design-questions/018g/` (`lead-engineer.md`, `principal-engineer.md`, `senior-manager.md`, `director.md`) following `prompts/DESIGN_QUESTIONS.md`, update the index and `PROJECT_STATUS.md` / `DECISIONS.md`. Append only a dated entry to `prompts/chatgpt-conversation.md`, preserving all prior content. Commit, push, and **STOP for ChatGPT review**. Do not begin Step 018h.
