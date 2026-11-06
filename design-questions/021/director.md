# Director — Step 021: immutable per-attempt GCS records

**Step context:** Step 021 added `llm_metrics/object_results.py`: a versioned, canonical single-JSON-object record per benchmark attempt (`llm-metrics.attempt.v1`), a create-only Google Cloud Storage writer (`ifGenerationMatch=0`, content MD5, bounded storage retries with byte-compare reconciliation), a read/validate path and an exact mapping to the existing SQL rows. It is offline-tested only (fake store and the real GCS client over a fake HTTP session) and deliberately not wired into the paid execution path.

---

## Question

What does moving results from per-run Cloud SQL to append-only object storage change in cost and in what the product can credibly claim, and is it the right investment before the first publishable dataset?

## Answer

**Cost structure changes from fixed to marginal:**

| Store | Cost | Operational burden |
|---|---|---|
| Always-on Cloud SQL | about $9.40/month before a single measurement | standing instance |
| Per-run Cloud SQL (Step 020) | about $0.004 per run | about 25 minutes of manual provisioning per run |
| GCS records | about $0.02/month at one model every 15 minutes (96/day, ~2,880 objects/month, ~32 MB/year) — inside the free tier; about $0.07/month for four models | none standing |

The dominant cost becomes Cloud Run job time (roughly $0–13/month depending on cadence and model count) plus API spend (about $0.95/month for `gpt-6-luna` at 96/day). That is comfortably inside $10/day.

**Credibility:**
- Immutable, canonical, one-object-per-attempt records with stated null semantics and price basis are easy to audit: any published number can be traced to the exact objects behind it.
- Records are append-only and create-only, so history can't be silently rewritten.

**What it does not yet change:** there is still n = 2. Step 021 adds capability, not data. The investment pays off only if Step 022 and scheduling follow quickly.

## Critique

**Good:**
- The design removes the largest fixed cost and the most manual step from the pipeline before scaling, rather than after.

**Weak / missing:**
- Several engineering steps have passed since the last new data point.
- There's no stated target yet (attempts per day, days of history, budget) to judge the collector against.

**Stronger:**
- Commit to a concrete data goal with the next approval. For example: 96 OpenAI attempts per day for 14 days at under $1/day all-in, then the first static snapshot.
- Measure Step 022 by records collected, not by components built.
