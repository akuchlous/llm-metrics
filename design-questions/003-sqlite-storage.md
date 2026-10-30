# Step 003 — SQLite persistence

## Lead engineer: Critique the `observations` schema, especially `value_ms` and `environment`.

**Sample answer:** One narrow table: `recorded_at`, `environment`, `provider`, `model`, `metric`, `value_ms`. `environment` has a `CHECK` constraint so only `test` or `prod` can be stored, which keeps simulated and real data apart. `value_ms` makes the unit explicit.

- **Good:** Enforces the most important invariant (provenance) in the database itself, not just in application code.
- **Weak:** `value_ms` couples the schema to one unit. Throughput (tokens/s) or cost ($) won't fit without a rename or a second column. Text columns for provider and model allow typos to split one series into two. There's no column for the request context (prompt size, region), which will matter for benchmarking.
- **Improve:** Acknowledge the deliberate deferral and its trigger: "the first non-millisecond metric forces either a `value` + `unit` pair or a separate table." Show you know the alternatives and why they were premature for Step 003. Don't add them now.

## Principal engineer: There are no migrations; the schema is created on every connect. When does this break, and what's the minimum fix?

**Sample answer:** It's fine until we change the schema. `CREATE TABLE IF NOT EXISTS` won't alter an existing table, so a new column would be silently missing on old databases.

- **Good:** Identifies the exact failure: a silent mismatch, not an error.
- **Weak:** No concrete mitigation. Misses that Step 004 already worked around this once (`CREATE UNIQUE INDEX IF NOT EXISTS`), which is an early sign the approach is under strain.
- **Improve:** Propose the smallest durable mechanism: SQLite's `PRAGMA user_version` with an ordered list of upgrade functions run in `connect()`. That's about 20 lines, needs no framework, is testable, and fails loudly on an unknown version. Adopt it the first time a column is added, not before.

## Senior manager: How do you make sure tests never pollute a developer's real data?

**Sample answer:** Tests use temporary directories, and the CLI tests set `LLM_METRICS_DB_PATH` to a temp file. We verified that running the suite doesn't create `data/`.

- **Good:** Describes both the mechanism and how it was verified.
- **Weak:** Relies on every new test remembering to set the override. One forgotten subprocess test would write to the real database without anyone noticing.
- **Improve:** Make the safe path the default for tests, for example a shared helper that always sets a temp database. Or a check in the test runner that fails if `data/llm_metrics.db` changed. Fail-safe defaults beat reviewer vigilance.

## Director: Is SQLite the right storage choice? What does reversing it cost later?

**Sample answer:** SQLite is perfect for a local tool: no server, no cost, and it ships with Python. If we outgrow it we can move to Postgres.

- **Good:** Matches the tool to the current need, and avoids running infrastructure prematurely.
- **Weak:** "We can move to Postgres" understates the cost. Hidden coupling grows: SQLite-specific SQL, text timestamps, `INSERT OR IGNORE`. It also doesn't say what would trigger the move: concurrent writers, multiple machines, or shared or public data.
- **Improve:** Name the triggers (multi-node collection, concurrent writers, public hosting). Keep all SQL in `storage.py` so a migration has a small blast radius; the project already does this. Note that the data volume of hourly benchmarks stays tiny for years, so the likely trigger is sharing, not scale.
