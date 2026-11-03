# Step 018d — Lead engineer

**Step context:** Step 018d fixed two correctness defects found in 018c review: `spend_by_model`'s ORDER BY used a bare column under GROUP BY (PostgreSQL strict mode rejects it), and `_ensure_schema()` silently stamped an unknown PostgreSQL schema.

**Question:** Why did `r.c.total_cost.is_(None)` work in SQLite but raise a `GroupingError` in PostgreSQL, and how was it fixed?

## Answer

SQLite does not enforce that every ORDER BY expression be either in the GROUP BY clause or an aggregate function. PostgreSQL applies SQL standard rules strictly: any column reference in ORDER BY that is not in GROUP BY must be wrapped in an aggregate. `r.c.total_cost.is_(None)` is a bare column reference; since `total_cost` is not in `GROUP BY (provider, model)`, PostgreSQL raises `GroupingError`. The fix replaces it with `func.sum(case((is_success, r.c.total_cost), else_=None)).is_(None)` — the same aggregate expression already used in the SELECT clause. This expresses the same intent (put groups with no successful cost last) while being valid SQL under both dialects.

## Critique

- **Good:** The fix uses the same aggregate expression that already appears in SELECT, so there is no new sub-expression to maintain.
- **Weak:** The bug was hidden because all prior tests ran against SQLite only. A single multi-dialect spend test would have caught it before the PostgreSQL integration step.
- **Improve:** Add the spend aggregation test to the offline test suite using an in-process SQLite database, and explicitly comment that ORDER BY must use aggregates to remain PostgreSQL-compatible.
