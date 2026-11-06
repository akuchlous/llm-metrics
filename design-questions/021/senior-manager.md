# Senior manager — Step 021: immutable per-attempt GCS records

**Step context:** Step 021 added `llm_metrics/object_results.py`: a versioned, canonical single-JSON-object record per benchmark attempt (`llm-metrics.attempt.v1`), a create-only Google Cloud Storage writer (`ifGenerationMatch=0`, content MD5, bounded storage retries with byte-compare reconciliation), a read/validate path and an exact mapping to the existing SQL rows. It is offline-tested only (fake store and the real GCS client over a fake HTTP session) and deliberately not wired into the paid execution path.

---

## Question

The team could have pointed the existing Cloud Run Job at a bucket and started collecting. Why ship a storage component that nothing calls yet, and what is the safe rollout from here?

## Answer

**Why not wire it in directly.** `real_benchmark.run()` requires PostgreSQL for cloud origin (018h), and `run_attempt()` writes through SQLAlchemy *after* the paid call. Redirecting persistence without a proven writer and a preflight could produce paid-but-lost measurements — the exact failure the 018h guard was built to prevent. So Step 021 proves the contract in isolation:
- 43 offline tests, including fault injection (lost acknowledgements, conflicts, bounded retries)
- the real GCS client driven over a fake HTTP transport
- an exact mapping to today's SQL rows

The paid path is provably untouched: a boundary test fails if `benchmark.py`, `real_benchmark.py` or `real_smoke.py` reference the module, and Docker `./run.sh test` passed twice (487 tests, 5 known skips).

**Rollout:**
1. *Step 021 (done):* offline component.
2. *Step 022, with explicit approval:*
   - a private bucket and least-privilege IAM (object create and get only)
   - a GCS preflight
   - one OpenAI run writing a real object, verified by independent download
   - the guard semantics kept: no durable target, no paid call
3. *Later:* scheduling, at a fixed cadence with a budget, and static snapshots (D069).

Each stage gets its own approval and its own stop for review.

## Critique

**Good:**
- Risk retired early and cheaply: no cloud spend, no change to the production job.
- Rollback is trivial, because nothing depends on the module yet.

**Weak / missing:**
- The production image grew by about 69 MB for a dependency that is unused until Step 022, which is deploy-time cost without value yet.
- Some confidence is borrowed from fakes: real IAM, Cloud Run ADC and retention settings are unproven.

**Stronger:**
- Write Step 022's acceptance criteria now. For example: "one object created, re-download sha256 matches, replay returns `created=False`, conflicting write is refused, guard still refuses with no bucket configured".
- Time-box the GCS dependency: if Step 022 slips, consider moving the dependency out of the production image.
