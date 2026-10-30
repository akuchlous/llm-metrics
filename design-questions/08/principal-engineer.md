# Step 08 — Principal engineer

**Step context:** Step 008 measured total response latency (`total_latency`) alongside TTFT from one streamed request, saved both as separate rows in one transaction, and added a TTFT / Total latency selector to the time-window dashboard.

**Question:** You added a second metric without a schema change. Does "one row per metric" hold up as metrics grow (throughput, errors, cost), and where does it break?

## Answer

It holds well for **scalar, per-request, millisecond metrics**. `ttft` and `total_latency` are just two values of `metric`; the unique index already includes `metric`, so both rows can share `recorded_at`; and the time-window query, percentile code and dashboard were reused unchanged with `metric` as a filter. Zero migration, and populations can't mix because every query filters by `metric`.

Where it strains, in the order we'll meet it:

1. **Units.** Throughput (tokens/s) doesn't fit `value_ms`. That needs either a `unit` column, a unit encoded per metric in code, or renaming to `value` (a versioned schema change; see 03).
2. **Request identity.** TTFT and total for one request are paired only by the identical `recorded_at`. Derived metrics (e.g. generation time = total − TTFT, or tokens/s) need a reliable join key: a `request_id`.
3. **Non-scalar outcomes.** Errors and availability are counts or ratios over requests, not per-request milliseconds. They fit better as a request-level table (status, error type) from which metrics are derived.

## Critique

- **Good:** The smallest change that met the requirement, with no speculative columns and no metric framework.
- **Weak:** The design implicitly assumes every metric is in milliseconds and independent. The `recorded_at` pairing is an accidental join key that will break the first time two requests from different workers share a microsecond, or rows are imported from elsewhere.
- **Improve:** In the first step that needs a derived or per-request metric, introduce a `requests` table (id, timestamp, provider, model, outcome) and make observations reference it. Write the "metric catalogue" (name → unit, description) down as a decision before adding the third metric.
