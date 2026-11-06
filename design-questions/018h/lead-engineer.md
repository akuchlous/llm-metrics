# Step 018h — Lead engineer

**Step context:** Step 018h adds a fail-closed guard in `real_benchmark.run()` that
rejects non-local-origin paid benchmark calls unless `LLM_METRICS_DATABASE_URL` is
explicitly set to a PostgreSQL URL, preventing silent data loss to ephemeral
container storage.

**Question:** The guard calls `os.environ.get(config.DATABASE_URL_VARIABLE, "")` to
read the raw URL value, rather than calling the existing `config.get_database_url()`.
Why? What would go wrong if `config.get_database_url()` were used instead?

## Answer

`config.get_database_url()` is designed to always succeed: when
`LLM_METRICS_DATABASE_URL` is not set, it falls back to
`sqlite:///<LLM_METRICS_DB_PATH>`. That fallback is the exact behavior the guard
exists to prevent for cloud-origin runs. Calling it would always return a URL —
either the configured one (possibly SQLite) or the fallback SQLite path — and the
guard could never detect the "not configured" case.

By reading the raw environment variable directly, the guard can distinguish between:
- Not set (empty string from `os.environ.get(..., "")`) → reject
- Explicitly set to SQLite → reject
- Explicitly set to PostgreSQL → pass

The guard only reads the raw value to categorize it; it does not parse or validate
it beyond the scheme check. If the URL passes the guard, `config.get_database_url()`
is called next by the existing code path, which performs the scheme validation that
`config` owns. This avoids duplicating config logic.

The comment in the guard documents why: "do not allow fallback to
`LLM_METRICS_DB_PATH`" is an invariant that cannot be expressed through
`get_database_url()` itself.

## Critique

- **Good:** The separation of "is this explicitly configured?" (guard, using raw
  env) from "what is the final DB URL?" (config, with its fallback) is a clean
  responsibility split. Each function does one thing.
- **Weak:** The guard duplicates one piece of knowledge: which schemes are
  PostgreSQL-valid (`postgresql` / `postgresql+psycopg2`). This is also known
  by `config._VALID_DB_SCHEMES`. If a third PostgreSQL driver scheme were added
  to config, the guard's `_CLOUD_APPROVED_DB_SCHEMES` would also need updating —
  there is no compile-time enforcement of their consistency.
- **Improve:** Add an assertion or unit test that
  `_CLOUD_APPROVED_DB_SCHEMES.issubset(config._VALID_DB_SCHEMES)` to prevent
  config adding a valid PostgreSQL scheme that the guard would reject. Or export
  `_VALID_DB_SCHEMES` from config and derive `_CLOUD_APPROVED_DB_SCHEMES` from
  it by exclusion.
