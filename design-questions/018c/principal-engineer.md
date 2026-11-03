# Step 018c — Principal engineer

**Step context:** Step 018c added `LLM_METRICS_DATABASE_URL`, a dialect-aware storage layer, and `psycopg2-binary` with a pinned hash — but all PostgreSQL tests are compile-only; no live server was available.

**Question:** What is the gap between "dialect compilation passes" and "PostgreSQL integration verified", and how should that gap shape the 018d deployment plan?

## Answer

Dialect compilation confirms that SQLAlchemy can generate syntactically valid SQL for a given dialect (CREATE TABLE DDL, INSERT … ON CONFLICT DO NOTHING). It does not exercise connection establishment, driver negotiation, transaction semantics, constraint enforcement, `alembic upgrade head` against a real catalog, or runtime type coercion differences (e.g. PostgreSQL's stricter UUID or timestamp types). The `DialectAndSchemaParityTest` tests verify only the compiled SQL string, not execution. Step 018c's report explicitly states "PostgreSQL integration not yet verified." This means 018d must include a pre-deployment integration test against Cloud SQL before routing any benchmark traffic: run `alembic upgrade head`, execute a round-trip save and load, and verify ON CONFLICT idempotency before promoting the image.

## Critique

- **Good:** Compile-only tests are honest and provide real value: they catch dialect-incompatible SQL that would only surface at runtime otherwise.
- **Weak:** The hash in `requirements.txt` covers only the Linux x86_64 cp313 wheel; any other platform or Python version used in CI or Docker will fail `--require-hashes` unless those hashes are also listed.
- **Improve:** Add a Cloud SQL smoke test to the 018d acceptance criteria; add the manylinux cp312 and musllinux wheels or the macOS arm64 wheel to `requirements.txt` for any contributor or CI platform that differs.
