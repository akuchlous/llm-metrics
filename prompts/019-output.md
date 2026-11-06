# Step 019 output — one-command disposable Docker local workflow

## Changed files

| File | Change |
|---|---|
| `compose.yaml` | New: Docker Compose local workflow; `db` service (postgres:17-alpine, tmpfs-backed named volume, no exposed ports); `app` service (Dockerfile.dev, `LLM_METRICS_COMPOSE_RUN=1`, `TEST_POSTGRES_URL` and `LLM_METRICS_DATABASE_URL` locked to Compose DB via service DNS; dashboard on `127.0.0.1:8000`) |
| `Dockerfile.dev` | New: dev/test image (python:3.13-slim); includes `tests/`, `docker/entrypoint.sh`; production `Dockerfile` unchanged |
| `Dockerfile.dev.dockerignore` | New: BuildKit per-Dockerfile ignore for dev builds; keeps `tests/` and `docker/` while excluding `.git/`, secrets, `data/`, `.venv/` |
| `docker/entrypoint.sh` | New: in-container entrypoint; runs all tests → seeds history → runs measurement → serves dashboard (serve mode) or HTTP smoke tests and exits (test mode) |
| `run.sh` | Rewritten as Docker Compose wrapper; requires `docker` and `docker compose`; prints clear prerequisite error when absent; supports `serve`, `test`, `down` modes; EXIT trap calls `compose down -v --remove-orphans` (project-scoped) |
| `tests/test_postgres_integration.py` | `setUpClass`: skips localhost-only hostname check when `LLM_METRICS_COMPOSE_RUN=1` (Compose service DNS allowed); always enforces disposable-dbname check. `tearDownClass`: no-op in Compose mode (volume handles cleanup). Added import: `from unittest import mock`. Added `PostgresGuardTest` class (7 safety unit tests, no live DB required). Module docstring updated. |
| `tests/test_run_script.py` | Rewritten for Docker-based `run.sh`; replaced `test_end_to_end_in_a_copy` (native Python) with Docker prerequisite tests: `test_no_docker_gives_helpful_error`, `test_no_compose_gives_helpful_error`, `test_invalid_mode_prints_usage`, `test_valid_modes_accepted` |

## Dependency and isolation model

- `db` service: `postgres:17-alpine`, named volume `llm_metrics_db_data` (disposable via `compose down -v`). No host port exposure; app reaches it only via service DNS `db:5432`. `LLM_METRICS_COMPOSE_RUN=1` is set in the app environment so test code trusts Compose isolation.
- `app` service: built from `Dockerfile.dev`; connects to Compose DB via `TEST_POSTGRES_URL` and `LLM_METRICS_DATABASE_URL` (both explicitly set in compose.yaml; inherited host env cannot redirect them). Dashboard bound to `0.0.0.0:8000` inside the container; exposed only on `127.0.0.1:8000` on the host.
- Compose project name `llm_metrics` scopes all resources. `compose down -v` removes the two containers, one network, and one named volume. Host images and unrelated volumes are untouched. No global prune.

## Test counts (offline, this machine)

```
Ran 433 tests in 10.154s
OK (skipped=13)
```

The 13 skipped tests are the PostgreSQL integration tests (`tests/test_postgres_integration.py::PostgresIntegrationTest`); they require `TEST_POSTGRES_URL`. They run inside Docker Compose where `LLM_METRICS_COMPOSE_RUN=1` and `TEST_POSTGRES_URL` are set.

## Docker runtime verification — UNVERIFIED (requires Cloud Shell)

Docker is not available on the development machine. The two clean `./run.sh test` cycles required by the acceptance criteria must be verified in Cloud Shell. Cloud Shell commands:

```bash
# Clone or pull the latest main
git clone https://github.com/akuchlous/llm-metrics.git
cd llm-metrics
# or: git pull origin main

# First clean run
docker compose down -v --remove-orphans 2>/dev/null || true
./run.sh test

# Second clean run (verify idempotency)
./run.sh test

# Confirm project-scoped resource cleanup
docker compose ps         # should show no containers
docker volume ls | grep llm_metrics  # should show nothing
docker network ls | grep llm_metrics # should show nothing

# Verify no unrelated images deleted
docker images

# Default serve mode (interactive)
./run.sh
# Ctrl+C → verify cleanup message and resource removal

# Recovery from SIGKILL
./run.sh down
```

Expected output for each `./run.sh test` cycle:
- All 433 tests pass, 0 skipped (integration tests run via Compose DB)
- `✓ Dashboard smoke test: HTTP 200`
- `✓ All done.`
- Cleanup: `Stopping and removing project Compose resources...`

## a20bf6f tearDownClass risk analysis

**Risk:** `tearDownClass` in `PostgresIntegrationTest` calls `pg_terminate_backend` and `DROP DATABASE` on the test database. A forwarded SSH tunnel (`ssh -L 5432:prod-db:5432`) makes a production database appear at localhost; the hostname check alone is not proof of safety.

**Mitigations in place (before Step 019):**
- `setUpClass` requires hostname in `{localhost, 127.0.0.1, ::1}` — rejects non-local URLs
- `_SAFE_DBNAME_RE` requires the database name to contain a recognizable disposable marker; `DROP DATABASE` is scoped to `cls.pg_url` which `setUpClass` validated

**Step 019 fix:**
- `tearDownClass` now returns immediately when `LLM_METRICS_COMPOSE_RUN=1`
- In Compose mode, the named volume is the source of truth; `compose down -v` destroys it completely. No `DROP DATABASE` is needed or appropriate.
- Outside Compose (manual localhost run), the existing guards still apply. The `DROP DATABASE` path is preserved for local cleanup.
- The fix addresses the prompt's concern that "a forwarded localhost port alone is NOT proof": inside Compose, isolation is proven by the `LLM_METRICS_COMPOSE_RUN=1` flag set only by compose.yaml; outside Compose, the guards are unchanged.

**Remaining residual risk (non-Compose):** SSH tunnel attack still possible if both hostname and dbname checks are defeated (attacker must control the database name). This was pre-existing; closing it fully requires client TLS certificate verification or a container-managed DB, which is exactly what Compose provides.

**Safety tests added:** `PostgresGuardTest` (7 tests) verifies the guard logic without a live database, covering non-localhost rejection, Compose service DNS acceptance, dbname enforcement in both modes, tearDownClass no-ops.

## Host image/cache caveat

After a Docker run, the host retains the `postgres:17-alpine` image and the locally built `llm_metrics-app` image in its Docker layer cache. This is normal. Build cache is not global-pruned by `run.sh`; it stays until explicitly removed with `docker rmi llm_metrics-app postgres:17-alpine` or `docker builder prune`. Re-runs use the cache, so subsequent builds are fast.

## Verified: no paid or cloud activity

- `APP_ENV=test` → DummyProvider; no real API keys, no real provider calls
- `LLM_METRICS_ORIGIN_CLOUD=local` → 018h cloud-origin guard does not fire
- No GCP resources created, modified, or executed
- Cloud Run Job (`llm-metrics-benchmark`) image `app:sha-9cf8ac9` unchanged and not executed

## One next step

Deploy the updated image to Cloud Run and re-execute exactly one controlled OpenAI measurement to verify the 018h guard is active in production, the new Docker Compose tooling builds a valid image, and PostgreSQL storage works end-to-end (Step 018i, deferred from before Step 019).

## MARKETING CHECKPOINT: not publishable yet

Stopping for ChatGPT review; Step 018i not started.
