# Step 11 — Principal engineer

**Step context:** Step 011 persisted every benchmark attempt with an outcome (`success` or a stable failure category: timeout, rate_limited, provider_error, transport_error, invalid_response), stored unknown token/cost facts as NULL with a `failed_after_ms` field, kept failed attempts out of latency/throughput observations, added an "observed benchmark success rate" with failures by category, and upgraded the schema to version 3 by rebuilding `requests`.

**Question:** You made unknown facts NULL, enforced it with a CHECK, and rebuilt the `requests` table to get there. Was that the right model and the right migration?

## Answer

**Model:** a failed attempt is still an attempt, so it belongs in the same table, which makes `COUNT(*)` the attempt count and the success rate a single `GROUP BY outcome`. Facts that are unknown for failures are NULL, not 0: a zero is a false measurement that would pull down averages and percentiles, while NULL means "unknown" and SQL aggregates skip it. The table CHECK encodes the invariant both ways, so neither application code nor a hand-written INSERT can store "a failed request that cost $0". `failed_after_ms` gets its own name, because overloading `total_latency` would silently change what every latency chart means.

**Migration:** making columns nullable needs a table rebuild in SQLite (there's no `ALTER COLUMN`). The version 2 → 3 step runs in the same `BEGIN IMMEDIATE` transaction as the version bump: create `requests_v3` from the single `_REQUESTS_TABLE` definition, copy every row with `outcome = 'success'`, drop, rename. Classifying Step-010 rows as successes is *true*, not assumed: Step 010 only ever saved completed requests. Unpaired observations aren't touched. This was verified against a database written by the actual Step 010 code, plus a test using the exact Step-010 DDL.

## Critique

- **Good:** It makes the invariant a database property, keeps history honest, and reuses one table definition for both fresh creation and the rebuild. The migration is atomic and tested on real data.
- **Weak:**
  - A table rebuild rewrites every row; that's trivial now but slow and lock-heavy for a large public dataset.
  - The CHECK lists categories inline, so adding one means another rebuild.
  - Observations still reference `requests (id)` without enforced foreign keys, so the rename and drop rely on SQLite's lenient behaviour.
  - Discarding partial TTFT removes a useful diagnostic.
- **Improve:**
  - Move the outcome vocabulary to a small lookup table (or drop it from the CHECK and validate in code), so new categories don't require rebuilds.
  - Turn on `PRAGMA foreign_keys` and verify the rebuild keeps references valid (`PRAGMA foreign_key_check` inside the upgrade).
  - Plan an explicitly named `first_output_ms` for failures, if streaming-failure diagnostics matter.
