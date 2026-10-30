# Step 07 — Director

**Step context:** Step 007 added 24h / 7d / 30d time windows to the dashboard (`/?window=`, default 7d), filtered in SQL relative to current UTC with inclusive bounds, so the count, chart, and p50/p95/p99 all come from the same rows.

**Question:** For an independent LLM benchmark, why do time windows matter, and what must be true before external users rely on these windowed numbers?

## Answer

Time windows turn a pile of measurements into claims people can act on: "over the last 24 hours, this provider's p95 TTFT was X". They show recent regressions (24h), weekly patterns (7d) and trends (30d). Without windows, every percentile is a lifetime average that hides incidents and recoveries.

Before external users rely on them:

- **Exact, published semantics:** UTC; inclusive bounds; anchored to current time; percentiles from exactly the plotted rows. All defined in D031 and stated on the page ("Window 7d: … to … (now), inclusive").
- **A sample size with every number.** The page now shows `n`; a 24h p99 from 20 points is noise and must look like noise.
- **One population per summary.** Today a window mixes seeded and live rows; with real data, each provider, model, region and source must be summarized separately.
- **Coverage transparency:** gaps in collection must be visible, not silently produce rosier percentiles.

## Critique

- **Good:** The semantics are precise, documented and test-backed, and the page states its window and `n`, which is the foundation of a credible benchmark.
- **Weak:** None of this is real data yet. Coverage (expected versus actual samples per window) isn't shown, so a window with missing hours looks the same as a complete one.
- **Improve:** When real collection starts, show coverage ("142 of 168 expected hourly samples"), hide or flag percentiles below a minimum `n`, and publish the window definitions in a methodology page that external readers can cite.
