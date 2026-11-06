# Lead engineer — Step 023: bounded 15-minute collector

**Step context:** Step 023 added `llm_metrics.scheduled_collector`, a no-argument 15-minute OpenAI collector. A job-environment policy allows exactly 96 UTC quarter-hour slots (24 h). Each paid request is gated by a create-only GCS claim per slot, read back and checked against GCS server time, with a 7-minute late limit and expiry rechecked before the call. A slot is never retried. It also added `collector_audit` (claims vs records), structured log events with ERROR/missed-run alerts, a dedicated Cloud Run Job and service account holding the only key access, and an invoke-only scheduler identity. The pilot was activated for 2026-11-06T18:00Z–2026-11-07T18:00Z.

---

## Question

Walk through why a create-only GCS object per slot prevents duplicate paid requests under concurrent or repeated deliveries. Which failure modes does the claim deliberately turn into "no request" rather than "retry"?

## Answer

**The claim is the lock.** Its name is a pure function of mode, profile, workload, origin and the UTC slot (for example `…/claims/prod/openai.gpt-6-luna.v1/interactive-chat-v1/gcp-us-central1/2026-11-06/1800.json`). The slot comes from the container clock, never from an argument; the command takes none.

GCS's `ifGenerationMatch=0` makes "create if absent" atomic on the server. Exactly one invocation per slot can create it, and every other one gets 412, or 403 with the object present, which becomes `ObjectExistsError` and then `duplicate_skip`, with no provider call.

The offline test runs 8 threads behind a barrier and gets 1 provider call, 1 claim and 1 record. The full-window test delivers every minute from 30 minutes before start to 30 minutes after expiry: 1,500 runs give **exactly 96** calls, 672 duplicate skips, 672 late refusals, and 30 no-ops on each side.

**Refusal, never retry:**

| Situation | Outcome |
|---|---|
| Ambiguous claim create (transient error; the object may exist) | `claim_failed`, exit 4 |
| Read-back mismatch | `claim_failed` |
| Server creation time more than 120 s from the local clock | `clock_skew` (slot consumed) |
| Expiry or late limit reached between claim and call | `expired_before_call` |
| Provider rejected the request | `provider_rejected` (slot consumed) |
| Record write failed | `not_persisted`, exit 3 |
| Process killed after the request | the next delivery for that slot finds the claim and skips |

In every case a later delivery for the same slot sees the claim and skips. The attempt id is minted before the claim, written into it, and reused as the record's id, so the audit can join them.

## Critique

**Good:** a single server-side primitive, no lease expiry logic, no database. The concurrency and full-window properties are tested rather than argued.

**Weak / missing:**
- A lost acknowledgement on the claim, or a clock-skew refusal, permanently burns the slot (deliberate, but it reduces coverage).
- The 7-minute late limit depends on startup latency: about 75–80 s was observed.
- The claim check relies on the overwrite being refused; whether that was 412 or 403 was not observed in the cloud.

**Stronger:**
- Record a `refused_after_claim` marker object, so the audit can tell refusals from crashes without logs.
- Alert if startup latency approaches the late limit.
