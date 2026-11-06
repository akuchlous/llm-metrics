# Senior manager — Step 022: GCS-backed OpenAI pilot

**Step context:** Step 022 added an explicitly selected GCS results backend to `real_benchmark` (`LLM_METRICS_RESULTS_BACKEND=gcs`; gcp origin and OpenAI only). It checks configuration before the key, runs a real create/read/no-overwrite storage preflight before the paid request, fixes the attempt id before the request and exits 3 if the record is not confirmed durable. It added a storage-only `gcs_smoke` command. In the cloud, the job service account proved storage with no provider key (Phase A), then one paid `gpt-6-luna` attempt was stored as an immutable `prod` object and independently verified (Phase B). The key was detached afterwards.

---

## Question

This step changed production code, created cloud resources and spent money. How was it sequenced and gated so that each failure would have been cheap, and what evidence would you require before approving scheduling?

## Answer

**Sequencing:**
1. *Phase 0 (no approval):** code, 24 new offline tests, a Docker suite of 511 tests with 5 known skips, production-image smoke, read-only inventory, official price recheck. Everything committed (`ee33635`) before any cloud action, so the build came from reviewed source.
2. *Phase A ("Approve A"):*
   - a private bucket, bucket-only IAM, a build and a job update; **no provider key**
   - one storage-smoke execution as the job service account, then operator re-download and SHA-256 comparison
   - verified that nothing existed under `prod`
   - worst case at this point: about $0 and a deletable bucket
3. *Phase B ("approved Step B"):*
   - attach only the key reference, after re-checking pricing, job settings and that nothing was running
   - execute once
   - **detach the key immediately, before verification**
   - verify independently

**Containment.** Each stage was a named subcommand of a committed script, and its output was inspected before the next. The idle job now refuses before any I/O.

**Evidence for a scheduling approval:**
- a defined cadence and daily cap (cloud + API)
- alerting on exit 3, on failed executions and on missed slots
- a probe lifecycle rule
- a rollback (pause the trigger)
- a bounded validation period with a review checkpoint

## Critique

**Good:**
- Approvals were specific and scoped; the destructive or costly part came last and was smallest.
- The key was detached before analysis, not after.

**Weak / missing:**
- The approvals are still conversational; no technical control stops a manual execution once a key is attached.
- One operator ran and verified everything.
- The owner-level `gcloud` login on the laptop persists.

**Stronger:**
- Before scheduling, enforce a budget at the provider (an OpenAI project spend limit) and give the scheduler a dedicated invoker service account.
- Have a reviewer check the stage logs.
