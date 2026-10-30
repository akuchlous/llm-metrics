# Step 03 — Lead engineer

**Question:** Critique the `observations` schema, especially `value_ms` and `environment`.

## Answer

The table is deliberately narrow: `id`, `recorded_at` (UTC ISO 8601 text), `environment`, `provider`, `model`, `metric`, `value_ms`, all `NOT NULL`.

- **`environment` with `CHECK (environment IN ('test','prod'))`** puts the most important invariant, provenance, in the database itself. No code path can store a third environment or omit it, so simulated rows can always be separated from real ones.
- **`value_ms`** matches the result dict and makes the unit explicit, which avoids silent unit bugs.
- **`recorded_at` as `...ffffffZ` text** sorts lexicographically in time order and is readable in any SQLite client.
- **SQL values always use `?` parameters**, and a test stores a SQL-injection string and reads it back literally.

## Critique

- **Good:** Small, explicit, and safe. Provenance is enforced, injection is tested, and the timestamps are sortable.
- **Weak:** `value_ms` ties the schema to one unit, so throughput (tokens/s) or cost won't fit without a schema change. Provider and model are free text, so a typo silently creates a separate series. `recorded_at` is the *save* time, about 100 ms after the request started, which is slightly imprecise for time-series analysis.
- **Improve:** Don't add columns speculatively, but write the trigger down: "the first non-millisecond metric introduces `value` + `unit` (or a separate table) via a versioned schema change." When real providers arrive, consider recording the request start time instead of the save time.
