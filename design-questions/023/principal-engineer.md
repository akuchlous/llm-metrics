# Principal engineer — Step 023: bounded 15-minute collector

**Step context:** Step 023 added `llm_metrics.scheduled_collector`, a no-argument 15-minute OpenAI collector. A job-environment policy allows exactly 96 UTC quarter-hour slots (24 h). Each paid request is gated by a create-only GCS claim per slot, read back and checked against GCS server time, with a 7-minute late limit and expiry rechecked before the call. A slot is never retried. It also added `collector_audit` (claims vs records), structured log events with ERROR/missed-run alerts, a dedicated Cloud Run Job and service account holding the only key access, and an invoke-only scheduler identity. The pilot was activated for 2026-11-06T18:00Z–2026-11-07T18:00Z.

---

## Question

The prompt asks for a hard 24-hour, 96-call ceiling that holds even if no one returns to turn things off. Where does the ceiling actually live, what can still bypass it, and how would you make it stronger without a database?

## Answer

**Where the ceiling lives (defence in depth):**
1. **Code:** the policy must be aligned and exactly 24 hours; outside it every delivery is a no-op with no I/O. Expiry and lateness are rechecked immediately before the request. A slot is claimed at most once.
2. **Configuration authority:** the policy lives in the job definition. The scheduler identity has `roles/run.invoker` (`run.jobs.run` only, no `runWithOverrides`), so it can neither override env vars or arguments nor update the job.
3. **Credential scope:** only `llm-metrics-collector@` can read `OPENAI_API_KEY`. The manual job's identity lost access in Phase A, so the credential-free manual job can't be quietly armed.
4. **Monitoring:** ERROR events, scheduler failures and an absence alert while active.

**What still bypasses it:**
- Anyone with project-level roles: they can update the job, grant secret access, or run arbitrary code with the key. The ceiling is on this code path, not on the account.
- An executor with override permission (the owner) could start a manual execution with a different policy, but it would still need an unclaimed in-window slot to spend.
- GCP charges in general (budgets alert only).
- The crash window after the paid response.

**Stronger, still without a database:**
- An **immutable policy object** in GCS (create-only, a hash pinned in the job env), so a changed env can't silently name a new window.
- An organisation policy or IAM deny for `run.jobs.runWithOverrides` on this job.
- An OpenAI project-level monthly budget as a hard cap on the provider side.
- A bucket retention lock on `claims/`, so claims can't be deleted to re-open slots.

## Critique

**Good:** the expiry doesn't depend on anyone remembering to pause, and every bypass needs a more privileged human action than the scheduler has.

**Weak / missing:**
- Policy integrity relies on IAM hygiene around the job, not on cryptography.
- Deleting a claim (an owner could) re-opens a slot.
- The key reference stays attached after expiry until someone runs `stop`.

**Stronger:** combine the policy object, a claims retention lock and a provider-side budget; then the ceiling survives even a mistaken job update.
