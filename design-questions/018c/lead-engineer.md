# Step 018c — Lead engineer

**Step context:** Step 018c made the storage layer genuinely dialect-aware: `connect()` accepts a URL string or Path, `_ensure_schema()` skips SQLite-only PRAGMA and legacy upgrade for PostgreSQL, and `save_new_observations()` dispatches to the correct dialect insert.

**Question:** What concrete changes were needed in `_ensure_schema()` to support PostgreSQL without breaking the SQLite legacy upgrade path?

## Answer

The function now branches on `engine.dialect.name`. For SQLite, the existing path is unchanged: read `PRAGMA user_version`, reject a newer database, call `_legacy_upgrade()` for a pre-Alembic database, stamp, and write the pragma back after a fresh schema creation. For PostgreSQL, `PRAGMA user_version` is not executed (it would raise a syntax error), `_legacy_upgrade()` is never called (the v0→v7 bridge is SQLite-specific), and a fresh database receives `alembic upgrade head` directly. A PostgreSQL database with existing tables but no `alembic_version` row is stamped at head, documenting that the operator already managed that schema. Both paths share the Alembic config setup and the `command.upgrade(alembic_cfg, "head")` call when a migration revision is present.

## Critique

- **Good:** The branching is explicit and contained in one function, so the SQLite path is unambiguous to read and test independently.
- **Weak:** The "stamp without upgrading" case for a PostgreSQL database that already has tables is an assumption that the schema matches head; if it does not, later migrations may fail or silently succeed on a partial schema.
- **Improve:** Add a `alembic current` check and warn when the detected revision is behind head; require an explicit operator flag to stamp an unmanaged PostgreSQL database rather than doing it silently.
