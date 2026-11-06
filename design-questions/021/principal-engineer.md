# Principal engineer — Step 021: immutable per-attempt GCS records

**Step context:** Step 021 added `llm_metrics/object_results.py`: a versioned, canonical single-JSON-object record per benchmark attempt (`llm-metrics.attempt.v1`), a create-only Google Cloud Storage writer (`ifGenerationMatch=0`, content MD5, bounded storage retries with byte-compare reconciliation), a read/validate path and an exact mapping to the existing SQL rows. It is offline-tested only (fake store and the real GCS client over a fake HTTP session) and deliberately not wired into the paid execution path.

---

## Question

The prompt says a GCS preflight cannot mathematically guarantee that a paid measurement is stored. Where exactly is the failure window, and what makes a stored record trustworthy as a scientific fact rather than just a JSON file?

## Answer

**The failure window.** In a future GCS-backed run, the sequence would be: preflight → provider call (money spent) → `measure_request` → `build_record` → `write_record`. Any of these breaks the chain after the money is spent:
- GCS unavailable for longer than the bounded retries
- the process killed (task timeout, OOM, preemption)
- IAM or the bucket changed mid-run
- a permanent read-back error

Step 021 makes the write idempotent and safe to replay. It does not close the window. The proposed Step 022 mitigations:
- generate the `attempt_id` before the call
- a `testIamPermissions` preflight as the GCS counterpart of the 018h guard
- a retry budget sized to the job timeout
- on a final failure, emit the canonical record (it contains no secrets by construction) to the log as a bounded failure report, with a distinct exit code, so the identical bytes can be replayed through `write_record` later
- never re-run the provider

**Scientific provenance:**
- **Frozen fact set:** `REQUEST_FIELDS` equals the SQL requests columns (test-pinned) and is frozen for v1. A new storage column can't silently change what a v1 record means.
- **Units by name:** observation units come from the `latency.METRICS` key, as in SQL.
- **Unknown stays unknown:** validation mirrors `ck_requests_outcome_consistency`, plus cached ≤ input and output ≤ cap. Unknown is `null`, never 0.
- **Auditable cost basis:** the price basis (input, output and cached rates) is stored per attempt.
- **Exact mapping:** `to_storage_rows` reproduces the SQL row exactly. This was tested against a real `run_attempt` stored in SQLite, and against the Step 020 PostgreSQL values.
- **Tamper evidence at read time:** the decoder rejects non-canonical, duplicate-key or misplaced objects.

## Critique

**Good:** the format is no richer than the trusted SQL facts. It adds no new measurement keys and invents no price provenance.

**Weak / missing:**
- There is no pricing *source* URL or verification date in the record; it's only in the code at run time.
- No code version or image digest is recorded, so a record can't say which build measured it.
- Observation integer ids aren't preserved, so importing into SQL renumbers them.

**Stronger:**
- A v2 schema could add run provenance: image digest, git SHA, price-table version.
- Design the post-response failure report and its replay path before the first GCS-backed paid run, not after the first lost record.
