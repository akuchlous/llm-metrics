# Step 07 — Lead engineer

**Step context:** Step 007 added 24h / 7d / 30d time windows to the dashboard (`/?window=`, default 7d), filtered in SQL relative to current UTC with inclusive bounds, so the count, chart, and p50/p95/p99 all come from the same rows.

**Question:** How does the time filter work, and what has to stay true for it to be correct?

## Answer

`load_observations(..., *, start, end)` adds `recorded_at >= ? AND recorded_at <= ?` to the existing parameterized query. The bounds come from `window_bounds(window, now)`, which returns `(now - window, now)`, and both bounds go through the same `format_timestamp` used on every write.

It compares **text**, not dates. That's correct only because every stored `recorded_at` has the identical fixed-width UTC format `YYYY-MM-DDTHH:MM:SS.ffffffZ`, so lexicographic order equals time order. Three invariants must hold:

1. Every write goes through `format_timestamp` (UTC, microseconds, `Z`).
2. Bounds are formatted the same way, so `2026-10-23T04:36:00.000000Z` compares correctly with `2026-10-23T05:00:00.000000Z`.
3. `now` is timezone-aware UTC (`datetime.now(timezone.utc)`), never naive local time.

Tests pin the edges: rows at `start - 1µs`, `start`, `end` and `end + 1µs` show both bounds are inclusive and future rows are excluded.

## Critique

- **Good:** One filtering rule in one place, parameterized, with boundary tests to the microsecond, and no schema change.
- **Weak:** The invariant is enforced only by convention. A row inserted by hand (`'2026-10-30 04:36'`, with a space and no `Z`) would silently sort wrong and appear in or vanish from windows. There's no index on `recorded_at`, which is fine at this size but a full scan as data grows.
- **Improve:** Enforce the format in the database with a `CHECK (recorded_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T*Z')` in the first versioned schema change, or store integer epoch microseconds. Add an index on `(environment, provider, model, metric, recorded_at)` once queries get slow; it matches the WHERE clause exactly.
