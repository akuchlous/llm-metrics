# Step 03 — Principal engineer

**Step context:** Step 003 persisted each successful TTFT measurement to a git-ignored SQLite file (`data/llm_metrics.db`) in one `observations` table with an `environment` column.

**Question:** There are no migrations; the schema is created on every connect. When does this break, and what's the minimum fix?

## Answer

`connect()` runs `CREATE TABLE IF NOT EXISTS` on every open. That's idempotent and gives zero-setup on a fresh clone. It breaks the first time the *table definition* changes: `IF NOT EXISTS` won't alter an existing table, so a new column is silently missing on older databases, and the failure appears later as a confusing SQL error.

We already hit the edge once. Step 004 needed a uniqueness constraint and avoided a migration by creating a separate `CREATE UNIQUE INDEX IF NOT EXISTS`, plus a test that seeds a database built with the Step 003 schema. That works for indexes, not columns.

The minimum durable fix needs no framework: store a schema version in SQLite's `PRAGMA user_version`, and keep an ordered list of small upgrade functions that `connect()` applies in one transaction. An unknown (newer) version fails loudly.

## Critique

- **Good:** Simple and correct for Steps 003–006. The old-schema test in Step 004 is exactly the kind of compatibility test a migration system needs anyway.
- **Weak:** The workaround pattern (`IF NOT EXISTS` for every new object) won't scale, and it isn't obvious to the next engineer which databases have which objects.
- **Improve:** Introduce `user_version` plus upgrade functions in the first step that changes a column, with a test that upgrades a database from each previous version. Not before.
