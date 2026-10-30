# Step 06 — Principal engineer

**Question:** The percentiles are computed over the seeded week plus live runs together. Is that statistically sound?

## Answer

Only as a consistency feature, not as statistics. The prompt asked for percentiles over "the same observations currently displayed", so the summary matches the chart. But the population is mixed: 168 synthetic hourly points with five injected spikes, plus a few live runs at about 100 ms. So p99 (472.3 ms) describes the spike injection, not any real behaviour.

Rules for when this becomes real data:

- **Compute over one coherent population:** one provider, model, environment, source and time window.
- **Never average percentiles.** A daily p95 can't be built from hourly p95s. Store raw values, or use a mergeable summary (histogram buckets, t-digest).
- **Watch for coordinated omission under load:** if a slow response delays the next request, the slow periods are under-sampled and the tail looks better than it is. Schedule requests on a fixed timeline, not "after the previous one finished".

## Critique

- **Good:** Implemented exactly what was asked, with the calculation isolated so changing the population later is a query change, not a rewrite.
- **Weak:** The summary invites over-interpretation. Nothing on the page says the population is mixed, and there's no way to filter seeded from live rows (see 04).
- **Improve:** Before real data, add source or time filtering to `load_observations`, and show the population next to the numbers ("n = 169, seeded + live"). Write the aggregation rules into `DECISIONS.md` now, before anyone builds a rollup.
