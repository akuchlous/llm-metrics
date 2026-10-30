# Step 09 — Senior manager

**Step context:** Step 009 added output throughput (`output_chunks_per_s` = (non-empty chunks − 1) ÷ (last − first chunk time)) to the single-pass measurement, renamed the stored `value_ms` column to `value` with the first versioned schema upgrade, and added the metric to the dashboard with correct units.

**Question:** This step changed the storage schema on every user's existing database. How do you ship a change like that safely when the only "deployment" is people running `./run.sh` on their own machines?

## Answer

The risk is irreversible data damage on machines we can't see, such as the owner's Chromebook database with real run history. Safeguards:

1. **Automatic, in-place, non-destructive upgrade.** `connect()` renames the column and keeps every row; there's no "delete `data/` and start over" instruction.
2. **Tested against the real old format,** not just a hand-written fixture: a database produced by the actual Step 008 code (170 rows) was upgraded by the new CLI, and every row survived.
3. **Refuse rather than corrupt.** Older code can't run against a newer database (version > `SCHEMA_VERSION` raises a clear error), so switching branches back can't silently misread data.
4. **Communicated where people look:** the README ("Older databases are upgraded automatically in place"), the status file, D018's revision note, and the step report.
5. **The one-command contract still holds:** `./run.sh` performs the upgrade transparently on its first run.

## Critique

- **Good:** Upgrade, test, refusal of newer databases, and documentation together form a credible change process for a tool with no central deployment.
- **Weak:** There's no backup before the upgrade, and no rollback path. Going back to Step 008 code after upgrading isn't supported (it's refused, which is safe but blocking). Users aren't told at runtime that an upgrade happened.
- **Improve:** Copy the database file to `llm_metrics.db.bak-v0` before the first upgrade step and print one line ("Upgraded database schema 0 → 1; backup at …"). Add a release note to the README for each schema version. This is cheap, and it turns "trust us" into "you can recover".
