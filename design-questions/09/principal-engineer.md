# Step 09 — Principal engineer

**Step context:** Step 009 added output throughput (`output_chunks_per_s` = (non-empty chunks − 1) ÷ (last − first chunk time)) to the single-pass measurement, renamed the stored `value_ms` column to `value` with the first versioned schema upgrade, and added the metric to the dashboard with correct units.

**Question:** The prompt said to reuse the observation model "if it remains correct". You changed the schema instead. Defend the decision and the migration approach.

## Answer

It didn't remain correct. The value column was `value_ms`; storing chunks/s there would make every reader of the database (SQL users, future code, exports) misinterpret throughput as milliseconds. Correctness ranks above minimal change (D016), and earlier design reviews had flagged `value_ms` as the first thing a non-millisecond metric would break.

The smallest correct change:

- **Rename `value_ms` → `value`**, and make the metric name fix the unit through one catalogue (`latency.METRICS`, D035). There's no `unit` column, because the name already determines the unit and a column would allow contradictions.
- **The first versioned migration:** `PRAGMA user_version`, with `_upgrade()` applying ordered steps in `connect()`. Version 0 → 1 checks `PRAGMA table_info` for `value_ms` and runs `ALTER TABLE … RENAME COLUMN`. Fresh databases are created at version 1. A database *newer* than the code is refused rather than misread.
- **Verified on a real file:** the Step 008 code created a version-0 database with 170 rows, and one run of the new CLI upgraded it with every row kept. Tests cover fresh, upgrade, re-upgrade and newer-version cases.

## Critique

- **Good:** It fixed the root problem instead of encoding a lie, used the lightest viable migration mechanism, and tested it against the real old format.
- **Weak:** The upgrade isn't wrapped in an explicit transaction: `ALTER TABLE` and `PRAGMA user_version` run as separate autocommitted statements, so a crash between them leaves a renamed column at version 0. That's recoverable, because the next run sees no `value_ms` and sets version 1, but only by luck of this particular step. Concurrent first connections (the CLI and dashboard starting together) are handled the same way. `RENAME COLUMN` also requires SQLite 3.25+, which is checked only implicitly.
- **Improve:** Run each upgrade step inside `BEGIN IMMEDIATE … COMMIT`, so the step and its version bump are atomic and concurrent upgrades serialize. Assert a minimum `sqlite3.sqlite_version` with a clear error. Keep a fixture database file for each past version in the tests.
