# Principal engineer — Step 024: offline analytics from immutable records

**Step context:** Step 024 added `llm_metrics.record_analytics`, an offline, read-only command that reads a local mirror of the immutable `llm-metrics.attempt.v1` GCS records (prod only), selects one exactly filtered population (provider, model, profile, workload, origin, UTC `[start, end)`), validates every candidate file with `object_results.decode_record`, and writes a canonical, create-only `llm-metrics.analytics.v1` summary. Slot completeness is reported only from collector claims via `collector_audit.audit`. It was tested on committed synthetic fixtures; no cloud or provider access was used.

---

## Question

Records alone show attempts, not the slots that never ran. Why does the summary obtain slot completeness by delegating to `collector_audit` over claims, and what guarantees that the claims-based slot counts and the records-based reliability numbers describe the same population?

## Answer

**Why claims:**
- A slot that produced no record (a missed scheduler delivery, a claim without a record, a late refusal) leaves no record to count. Inferring missing slots from gaps in `recorded_at` would invent a schedule the records don't encode.
- The claims are the collector's own evidence. `collector_audit.audit` already classifies each begun slot as `recorded_success`, `recorded_failure`, `claim_without_record` or `missing`. Reusing it keeps one definition of slot state.
- Without `--collector-policy-start`, `slot_completeness` is `null` and a `no_slot_evidence` caveat is written.

**Why the two sets agree.** `slot_evidence()` requires all of the following, and otherwise raises:
1. The population is exactly the collector's fixed scope (`scheduled_collector.TARGET`, `WORKLOAD_ID`, `ORIGIN_CLOUD`), and `--start` equals the policy start.
2. No selected record is in the audit's `records_without_claim`. Such a record would be a one-off or foreign record mixed into the scheduled population.
3. The audit's `recorded_success` / `recorded_failure` counts equal the selection's success / failure counts, and every recorded-failure attempt id is selected. This catches a window end that cuts off a begun slot's record (the test uses `--end 18:15:06Z`).
4. The audit runs with `now = end − 1 µs`, so a slot that begins exactly at `end` is outside `[start, end)`.

So "attempts" (6 in the fixture) and "slots" (8 begun: 5 success, 1 failure, 1 missing, 1 claim without record) are reported side by side, and are never added together.

## Critique

**Good:** one owner of slot semantics, and a strict equality check rather than a best-effort join. Missing slots never enter the reliability denominator, and they never silently disappear either.

**Weak / missing:**
- It is coupled to Step 023's fixed scope and 24-hour policy: windows longer than one policy, or a future multi-profile collector, are refused.
- The audit re-reads the policy's record days through its own loader. That is double I/O, but bounded.
- `audit` does not expose claimed ids for successful slots, so agreement is checked by counts plus failure ids, not by full id-set equality.

**Stronger:** have `collector_audit.audit` return the per-slot attempt ids (a small, reviewed change to the Step 023 module, after the pilot), then check set equality.
