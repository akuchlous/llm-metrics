# Step 10 — Principal engineer

**Step context:** Step 010 added a `requests` table (own UUID identity, provider-reported input/output tokens, requested max output tokens, effective per-1M prices, and unrounded costs) linked to the existing metric observations, a `Usage` event at the end of each stream, a single `pricing.py`, schema version 2, and a `/requests` view of individual calls.

**Question:** You introduced request-level facts next to metric observations. Walk through the data-model choice, the upgrade, and where this model will strain next.

## Answer

The core distinction: an **observation** is a measurement in a metric's unit, while a **request** is the unit of work. Tokens, the output cap, prices and costs are facts about the request; forcing them into `metric/value` rows would mix units (tokens, dollars, ms) in one column and turn "all metrics" queries into nonsense. So:

- **`requests`:** `id` (llm-metrics UUID), `recorded_at`, `environment`, `provider`, `model`, the token counts and cap, `input_price_per_1m`, `output_price_per_1m`, and the costs, with CHECK constraints on the counts, cap and prices.
- **`observations.request_id`:** a nullable reference. The aggregate queries are untouched, and the per-request view is one LEFT JOIN.
- **Upgrade to version 2:** `ALTER TABLE … ADD COLUMN request_id` plus an index, inside one `BEGIN IMMEDIATE` transaction with the version bump. That fixes the non-atomic upgrade flagged in the Step 09 review. Old rows keep `request_id` NULL and no `requests` rows are invented. It was verified on a real 171-row version-1 database.
- **UUID rather than integer ids,** so collectors on different machines can be merged later without colliding.

Where it strains next:

1. **Failed requests:** errors and timeouts (the next likely metrics) are request outcomes. `requests` needs a status and error fields, and today a failed request isn't stored at all.
2. **Workload dimensions:** prompt category or region are request attributes, so they belong on `requests`, not `observations`. That's good, because the table is already the right home.
3. **Duplicated identity columns:** `observations` still repeats `environment`, `provider` and `model` for request-linked rows (needed for unlinked historical rows). Normalising would require backfilling history, which we deliberately don't fabricate.

## Critique

- **Good:** It separated two kinds of data correctly with the smallest schema change, kept history honest, and made the upgrade atomic and verified on real data.
- **Weak:** `observations.request_id` has a REFERENCES clause, but SQLite doesn't enforce foreign keys unless `PRAGMA foreign_keys = ON` is set per connection, so the reference is documentation only. The duplicated identity columns could drift from the request row.
- **Improve:** Turn on `PRAGMA foreign_keys = ON` in `connect()` and add a test that an observation with an unknown `request_id` is rejected. Add a consistency test that linked observations match their request's provider, model and environment. Plan the `status`/`error` columns on `requests` for the error-metrics step.
