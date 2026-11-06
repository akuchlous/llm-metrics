# Director — Step 020: guarded second OpenAI cloud pilot

**Step context:** Step 020 replaced the pre-guard Cloud Run Job image with an immutable, digest-pinned build containing the 018h fail-closed cloud-origin database guard, proved the guard in the cloud with the model key detached (exit 2, "No request was made"), then under a separate approval ran exactly one OpenAI `gpt-6-luna` measurement into a temporary Cloud SQL PostgreSQL 17 instance, exported and independently verified a checksummed backup, and tore the database down.

---

## Question

Step 020 cost under one cent in cloud and API spend and produced a second data point. Was it worth a full milestone, and what does it change about the product timeline and credibility?

## Answer

**What it bought:**
1. **Risk retired:** the deployed job could previously spend money and silently lose the result (pre-guard image + no DB). It now runs a digest-pinned image that refuses such runs, and its idle state holds no credentials. That is a real security/cost liability closed in production, not just in source.
2. **A repeatable, auditable measurement path:** scripted inventory → deploy → negative proof → one paid run → verified backup → teardown, with every artefact in Git or in the private bucket. Anyone can re-run or audit it.
3. **Evidence about cost structure:** the measurement itself costs ~$0.0003; the infrastructure dance around it costs ~$0.004 and ~25 minutes of attention. The bottleneck to publishable data is *process*, not API spend.

**What it did not buy:** publishable metrics. Two samples (TTFT 2013 ms and 2470 ms) from one model, one region, both hitting the 300-token cap, are anecdotes. No percentile, trend or provider comparison is defensible yet.

**Timeline implication:** repeating this per measurement will not reach a credible dataset. The next investment should be a durable, low-cost recurring OpenAI-only collector plus static snapshot export (D069) — that is what turns the guarded path into a time series worth publishing.

## Critique

**Good:** spending was tiny and bounded by design; the milestone converted a known liability into a verified control; marketing restraint ("not publishable yet") was preserved.

**Weak / missing:** the 018f–020 pilot steps have produced n = 2. Without a decision on the recurring store and schedule budget, the project risks optimising safety ceremony instead of data volume.

**Stronger:** set an explicit target (e.g. N measurements/day for M days within $X/month) for the next step, so the collector design is judged against a product outcome rather than another single successful run.
