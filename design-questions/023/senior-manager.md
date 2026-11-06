# Senior manager — Step 023: bounded 15-minute collector

**Step context:** Step 023 added `llm_metrics.scheduled_collector`, a no-argument 15-minute OpenAI collector. A job-environment policy allows exactly 96 UTC quarter-hour slots (24 h). Each paid request is gated by a create-only GCS claim per slot, read back and checked against GCS server time, with a 7-minute late limit and expiry rechecked before the call. A slot is never retried. It also added `collector_audit` (claims vs records), structured log events with ERROR/missed-run alerts, a dedicated Cloud Run Job and service account holding the only key access, and an invoke-only scheduler identity. The pilot was activated for 2026-11-06T18:00Z–2026-11-07T18:00Z.

---

## Question

This step moved from a single supervised paid call to unattended recurring spend. How was the rollout staged, what happened that the plan didn't anticipate, and what is the operational handover once the session ends?

## Answer

**Staging:**
- **Phase 0:** code and 22 new tests (Docker suite: 533 tests, 5 skipped), committed (`1ce395c`) before any cloud change.
- **Phase A ("Approve A"), no key:**
  - Scheduler API; two service accounts.
  - Bucket-only grants; the manual job's key access removed.
  - A preflight-only lifecycle rule.
  - Build `13b90b82`, deployed by digest.
  - Scheduler created and paused immediately; invoker scoped to the job; email channel; three alert policies (missed-run disabled).
  - Dry-run, expired-policy and alert-test executions, plus independent verification.
- **Phase B ("Approve B"):** one `activate` stage, with a future start 12 minutes ahead.

**Surprises, reported rather than smoothed over:**
- The first dry run was submitted 8 minutes into a slot, and the gate correctly refused it as `late_start`. This revealed that execution startup takes about 75–80 s.
- An interrupted command had already launched one extra expired-policy dry run (a harmless no-op).
- The user asked for a 1-minute test cadence. That would have contradicted the 15-minute slot design, so the options were presented and the user chose to skip it.

**Handover:**
- After the session ends, the system stops spending at expiry by itself.
- The operator must later: run `audit` for the window; run `stop` to pause the scheduler, detach the key reference, remove secret access and disable the absence alert; review the alert emails.
- Alerts reach the user's email during the window.

## Critique

**Good:**
- The approvals mapped onto concrete stages.
- The gate's first real-world refusal happened in dry-run, at zero cost.
- The emergency stop is a single command.

**Weak / missing:**
- Alert delivery was confirmed only as matching log entries; receipt of the emails depends on the user checking.
- Nobody is on call; failures during the night are found in the morning.
- The final 96-slot outcome is not observed in this step.

**Stronger:**
- Schedule a calendar reminder for the post-window audit and `stop`.
- Have the audit email a summary.
- Run a fault drill (pause the scheduler for 45 minutes) to prove the absence alert fires.
