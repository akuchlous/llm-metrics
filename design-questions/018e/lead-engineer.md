# Step 018e — Lead engineer

**Step context:** Step 018e adds a minimal Dockerfile, pre-flight DB connectivity check, Gunicorn as the production WSGI server, configurable HOST binding, and a database-name safety guard on the destructive integration test harness — preparing the codebase for Cloud Run deployment without creating any cloud resources.

**Question:** The pre-flight DB check in `real_benchmark.run()` calls `storage.connect(db_path)` before the paid provider call. What class of failure does this catch, what does it not catch, and what is the right exit code for it?

## Answer

`storage.connect(db_path)` opens a database connection and runs `_ensure_schema()`, which applies any pending Alembic migrations. A failure here (network unreachable, wrong credentials, orphan-tables `RuntimeError`, or migration conflict) means the result of the paid call cannot be persisted. By returning exit code 2 before the provider call, the command preserves the invariant that any `real_benchmark` exit with no announcement means no money was spent.

What it does not catch: the connection may succeed at pre-flight time (the engine is cached in `storage._engines`) but the final `save_request` write can still fail — for example, because a concurrent `DROP TABLE` runs between pre-flight and save, or because a PostgreSQL transaction is aborted mid-flight. The pre-flight check eliminates the most common class of billed-but-unrecorded outcome (bad credentials, missing database, unresolved migration) without guaranteeing atomicity end-to-end.

The exit code is 2 (configuration error) rather than 1, consistent with the project's exit-code contract (D010): `0` = success, `2` = configuration or refusal before any request. The error message prints only the redacted URL (`_redact_db_url`) so credentials never appear in terminal output.

## Critique

- **Good:** Pre-flight runs before the "About to make" announcement, so the message "No request was made" is always accurate: no paid call was made when this error fires.
- **Weak:** The check connects and migrates the database (a schema migration could run here), but that migration would have happened anyway when `save_request` called `connect`. The only thing bought is early detection of connectivity failures — not full write-path proof.
- **Improve:** A more defensive approach would be to also run a lightweight write probe (e.g. insert and rollback a dummy row) to verify that the write transaction path works, not just the read connection. That is still not a guarantee, but it tightens the pre-flight.
