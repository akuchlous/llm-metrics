# Step 06 — Director

**Step context:** Step 006 added nearest-rank p50/p95/p99 TTFT to the dashboard and made `./run.sh` seed simulated history automatically in test mode (never in prod).

**Question:** Which latency number should be the headline when comparing providers: p50, p95, or p99?

## Answer

No single number. Headline **p50 and p95 together**, with p99 and the sample size one click away, all under a published method. The reasons:

- **p50** is the typical experience, and is stable with small samples.
- **p95** is what interactive users notice: a provider with a fast median but a bad p95 feels unreliable in chat.
- **p99** matters for SLAs and high-volume products, but needs n ≥ 100 to mean anything under nearest-rank, and is noisy otherwise.

The right emphasis depends on the scenario: interactive chat weights tails, while batch work weights p50 and throughput. A benchmark should also keep metric definitions stable over time, or trends become meaningless. And it should avoid a single ranking number that providers can tune for.

## Critique

- **Good:** The dashboard already shows all three, names the method, and keeps the calculation deterministic, which is a solid base for a fair headline.
- **Weak:** It doesn't show sample size, scenario, or confidence, so a reader can't tell a meaningful p99 from noise. And today all of it is simulated.
- **Improve:** When real data arrives, publish per-scenario views (chat vs. batch), show `n` and the time window with every percentile, and commit in writing to stable metric definitions, with versioned changes.
