# Principal engineer — Step 019: one-command disposable Docker local workflow

**Step context:** Step 019 replaced the native-Python `./run.sh` with a Docker Compose wrapper. The `compose.yaml` explicitly sets `TEST_POSTGRES_URL` and `LLM_METRICS_DATABASE_URL` in the app service environment so inherited host variables cannot redirect integration tests to a production database.

---

## Question

`compose.yaml` explicitly sets `TEST_POSTGRES_URL` to point at the Compose-managed PostgreSQL service. The integration tests use this URL to connect to the test database. Walk through the threat model for database URL injection — ways an operator's environment could redirect destructive SQL to a production database — and explain how the current design defeats each vector. Where does the design stop being right?

## Answer

**Vector 1: Inherited host `TEST_POSTGRES_URL`**
If a developer has `TEST_POSTGRES_URL=postgresql://user:pass@prod-db/testdb` set in their shell, running `docker compose up` without an explicit override in `compose.yaml` would pass that URL into the container.

*Defense:* `compose.yaml` sets `TEST_POSTGRES_URL: "postgresql://llm_metrics:llm_metrics_test_pass@db/llm_metrics_test"` as a concrete value, not a variable reference (`${TEST_POSTGRES_URL}`). Docker Compose resolves this to the literal string; the host's `TEST_POSTGRES_URL` is ignored for this service.

**Vector 2: Inherited host `LLM_METRICS_DATABASE_URL`**
Similarly, the application DB URL used by `seed_history` and `real_benchmark` could be inherited from the host.

*Defense:* Same as above — both `LLM_METRICS_DATABASE_URL` and `TEST_POSTGRES_URL` are explicitly valued strings in `compose.yaml`.

**Vector 3: `setUpClass` hostname check bypassed inside Compose**
Step 019 relaxes the hostname check when `LLM_METRICS_COMPOSE_RUN=1`. An operator could set this flag on the host and also set `TEST_POSTGRES_URL` to a production server.

*Defense:* The `_SAFE_DBNAME_RE` dbname check still applies in Compose mode. The `compose.yaml` DB name is `llm_metrics_test` (matches the `test` marker). This is a weaker guard than structural isolation, but it requires the attacker to defeat both the flag and the dbname pattern.

**Vector 4: Compose project name collision**
Another Compose project named `llm_metrics` could have a `db` service with a different database URL, and `app` from this project could accidentally connect to it.

*Defense:* Docker Compose service DNS resolves `db` to the container within the same Compose network, not any other network. Two `llm_metrics` projects would not share a network unless explicitly configured with external networks. This vector is effectively closed.

**Where the design stops being right:**
The design assumes Docker and Compose isolate the container network correctly. If the developer's Docker daemon is misconfigured (e.g., a custom `network: host` mode in a modified compose.yaml), all network isolation breaks. The design also does not use Docker secrets for the test database credentials — they appear as plaintext in compose.yaml, which is acceptable for disposable test credentials but would be wrong for any shared environment.

For a team environment (CI runner, shared dev box), the fixed credentials in compose.yaml would be a secret rotation burden. The correct fix is to use Compose variable substitution from an `.env` file (git-ignored) or a secrets manager, with the compose.yaml only holding the form `postgresql://llm_metrics:${PG_TEST_PASS}@db/llm_metrics_test`.

## Critique

**Good:** Locking both URL variables as concrete strings in compose.yaml is a simple and effective defense against the most common injection vector (inherited host env). It is auditable by reading compose.yaml.

**Weak:** The test credentials are hardcoded in compose.yaml and checked into Git. For a single-developer project with a disposable local database, this is a low-severity issue. For any shared use, it creates a credential rotation burden.

**How to improve:** Move the PostgreSQL password to a `.env` file that compose.yaml reads via `${LLM_METRICS_TEST_PG_PASS}`, add `.env` to `.gitignore`, and document the setup in README. Add a check in `run.sh` that refuses to run if the `.env` file is absent, so the developer cannot silently inherit the default plaintext credential.
