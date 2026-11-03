# Step 018b — Lead engineer

**Step context:** Step 018b replaced direct `sqlite3` storage operations with SQLAlchemy Core and introduced an Alembic v7 baseline, retaining local SQLite.

**Question:** How did the migration preserve atomic writes and the difference between an unknown value and zero?

## Answer

`storage.save_request` now uses SQLAlchemy Core inserts within `engine.begin()`, so a request and its observations commit or roll back together. Existing schema CHECKs still require known token/cost values on success and NULL values on failure; failed attempts have no metric observations. The legacy v0–v7 path preserves historical unknown facts rather than backfilling guesses. Tests changed their expected exception wrapper to `sqlalchemy.exc.IntegrityError` while retaining assertions on invalid data.

## Critique

- **Good:** Focuses on behavior and data semantics, not just passing query syntax through a new library.
- **Weak:** The report shows offline SQLite tests, not a PostgreSQL transactional integration test.
- **Improve:** Exercise these invariants against a disposable PostgreSQL database when available, including rollback and constraint rejection.
