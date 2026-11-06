# Lead engineer — Step 021: immutable per-attempt GCS records

**Step context:** Step 021 added `llm_metrics/object_results.py`: a versioned, canonical single-JSON-object record per benchmark attempt (`llm-metrics.attempt.v1`), a create-only Google Cloud Storage writer (`ifGenerationMatch=0`, content MD5, bounded storage retries with byte-compare reconciliation), a read/validate path and an exact mapping to the existing SQL rows. It is offline-tested only (fake store and the real GCS client over a fake HTTP session) and deliberately not wired into the paid execution path.

---

## Question

`write_record` treats "the object already exists" as success in one case and as an error in another. Walk through how create-only writes, byte comparison and bounded retries give exactly-once storage of one attempt — including when the first upload's acknowledgement is lost.

## Answer

**Identity first.** The object name is `<prefix>/v1/requests/<env>/<date>/<attempt_id>.json`, a pure function of the record. `attempt_id` is llm-metrics' own random UUID, so two different attempts never share a name. The provider request id is deliberately not in the name: it can be missing, and it is not ours to keep unique.

**Canonical bytes.** `encode_record` gives one byte string per record (sorted keys, fixed separators, ints normalised to floats for amounts, no NaN). Equal facts mean equal bytes, so "same record" can be checked with `==` on bytes.

**The loop (max 3 attempts, backoff 0.5 s and 2.0 s):**
1. `create` with `ifGenerationMatch=0` — the server writes only if no object exists, atomically.
2. Read back.
   - Created and the bytes match ⇒ durable (`created=True`).
   - Got 412, and the bytes match ⇒ durable (`created=False`): either an idempotent replay or our own earlier write.
   - Got 412, and the bytes differ ⇒ `RecordConflictError`; nothing is overwritten.
   - Created, but the read-back is missing or differs ⇒ `RecordIntegrityError`.
3. A transient error (503, reset, timeout) is ambiguous: the server may have committed the object. The next create-only call resolves it, either by succeeding or by returning 412 followed by a matching read. Tested both with `FakeStore` (`transient_after`) and through the real client (`commit+503`, then 412).

**What the real client does.** `GcsObjectStore` passes `retry=None`, so the library cannot add hidden retries, and sets `md5Hash` so the server rejects corrupted uploads. The fake-session test asserts `ifGenerationMatch=0` and `md5Hash` in the actual multipart request.

## Critique

**Good:**
- The duplicate semantics are explicit and tested, including concurrent writers and lost acknowledgements.
- Errors carry names, never content.
- The library's retries are switched off, so the writer is the only retry policy.

**Weak / missing:**
- `created=False` mixes "an identical replay by another process" with "our own late acknowledgement". That's fine for durability, but less useful for operations.
- A permanent error on the read-back after a confirmed create surfaces as a generic `ResultStoreError`, even though the object most likely exists.
- The real-server 412/MD5 behaviour is only modelled, not observed.

**Stronger:**
- Return the object generation from the create and compare it on read (`if_generation_match=<gen>`), so a read can't race a delete-and-recreate.
- Distinguish "durability unknown" from "failed" in the error type.
- Prove the 412 and MD5 behaviour once against a real bucket in Step 022.
