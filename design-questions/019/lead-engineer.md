# Lead engineer — Step 019: one-command disposable Docker local workflow

**Step context:** Step 019 replaced the native-Python `./run.sh` with a Docker Compose wrapper that builds a self-contained `app` + `postgres` environment, runs all tests (including PostgreSQL integration tests), seeds simulated history, runs a measurement, and serves the dashboard — cleaning up all project-scoped containers, network, and volume on exit.

---

## Question

`tearDownClass` in `PostgresIntegrationTest` calls `pg_terminate_backend` and `DROP DATABASE` after the test run. The step changes this to a no-op when `LLM_METRICS_COMPOSE_RUN=1`. Walk through the full safety model: what does each guard check, what does it protect against, what residual risk remains, and why does the Compose flag close it?

## Answer

**Four-layer guard model:**

1. **`setUpClass` hostname check (outside Compose):** `parsed.hostname not in ("localhost", "127.0.0.1", "::1")` skips the class if the URL points anywhere but loopback. Protects against accidental `TEST_POSTGRES_URL=postgresql://prod-host/testdb` running destructive tests against a production or shared server.

2. **`_SAFE_DBNAME_RE` check (always):** Requires the database name to contain `test`, `dev`, `bench`, `tmp`, `temp`, or a step suffix (e.g. `018d`). Protects against SSH tunnels: `ssh -L 5432:prod-db:5432` makes a production database appear at `localhost:5432`, defeating the hostname check alone. The attacker must also control the database name.

3. **`tearDownClass` hostname check (implicit):** `tearDownClass` relies on `cls.pg_url` only being set when `setUpClass` passed. So `DROP DATABASE` is called only on URLs that passed both checks above.

4. **`LLM_METRICS_COMPOSE_RUN=1` guard (Step 019):** When this flag is set (by `compose.yaml` only), `tearDownClass` returns immediately — no `pg_terminate_backend`, no `DROP DATABASE`. Compose owns cleanup through the named volume (`compose down -v`). The flag is set exclusively inside the `compose.yaml` environment stanza; a developer running tests manually outside Compose does not have it, so the existing guards still apply.

**Why the flag closes the residual risk inside Compose:** The SSH-tunnel attack requires the developer to have configured both `LLM_METRICS_COMPOSE_RUN=1` and a tunnel to production — an implausible combination because Compose sets the flag precisely to signal it has already established the isolated Compose DB. Outside Compose, the hostname + dbname guards are the defense; inside Compose, isolation is structural (the `db` service has no external port).

**Residual risk (non-Compose):** A developer who sets up an SSH tunnel to production, names the target database `test_prod`, and runs the integration tests manually would hit `DROP DATABASE`. Closing this fully requires mTLS or a URL allowlist, which is not implemented.

## Critique

**Good:** The Compose flag is a clean, explicit contract: the operator opts into trusting Compose isolation by setting it. `tearDownClass` doing nothing in Compose mode is correct because the disposable volume makes DROP DATABASE redundant. The offline safety tests in `PostgresGuardTest` verify the guard logic without requiring a live database.

**Weak:** The `LLM_METRICS_COMPOSE_RUN` flag is advisory — an operator could set it manually outside Compose and bypass the hostname check. A stronger design would verify the flag against something only Compose can provide (e.g. a Compose-generated secret or a network namespace check), but no such mechanism exists in Compose.

**How to improve:** Use `POSTGRES_HOST=db` (a Compose-only service DNS name) as the disposability signal instead of a separate flag: if the hostname in `TEST_POSTGRES_URL` is `db` and there is no `db` host reachable via system DNS (confirmed by a socket connect to that hostname, not just a name check), the test knows it is in Compose. This would not close the residual risk fully either, but it makes the guard harder to defeat accidentally. Alternatively, add `DB_OWNER=compose` to the postgres service labels and read it via the Docker API from the test runner — but that requires a Docker socket in the test container, which introduces its own risks.
