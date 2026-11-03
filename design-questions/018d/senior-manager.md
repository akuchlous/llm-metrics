# Step 018d — Senior manager

**Step context:** Step 018d ran 13 integration tests against a real local PostgreSQL 17 database and found two defects (silent schema stamping and a GROUP BY ordering bug) that were not visible in the offline test suite.

**Question:** What does the discovery of two correctness bugs in Step 018d reveal about the limits of dialect-compilation testing, and how should the review process account for this?

## Answer

Step 018c's compile-only tests proved that SQLAlchemy could generate syntactically valid SQL for both dialects, but they did not execute that SQL. Step 018d found that the generated SQL, while syntactically valid, was semantically rejected by PostgreSQL's strict GROUP BY enforcement, and that the migration lifecycle code had unsafe conditional logic. Both bugs were invisible to offline tests because SQLite is permissive on GROUP BY ordering and has no concept of an unknown Alembic revision in the context of a silent stamp. This shows that "compiles for dialect X" is a necessary but not sufficient condition for "runs correctly on dialect X." The review process should require a real execution gate (like Step 018d's integration tests) before any step can claim PostgreSQL correctness, not just compilation correctness. Step 018c's "not yet verified" label was accurate; Step 018d closed the gap. Future steps that touch SQL queries or schema lifecycle code should include a corresponding integration test case.

## Critique

- **Good:** The staged approach (018c: compilation; 018d: execution) kept each step reviewable on its own, made the defects easy to locate, and avoided a longer, harder-to-review combined step.
- **Weak:** The bug in `spend_by_model` existed since Step 017 and was not caught earlier because no integration test covered that function against a strict-GROUP-BY database.
- **Improve:** Establish an explicit policy: any SQL expression change must include a test that exercises it against a real database (SQLite in the offline suite is acceptable for most cases, but a GROUP BY ordering test with GROUP BY would have caught this).
