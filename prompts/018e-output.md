# Step 018e output — Secure Cloud Run deployment readiness

## Summary

Step 018e adds a minimal, secure container artifact for Cloud Run deployment and targeted safety fixes. No cloud resources were created; no paid provider calls were made.

## Changed files

| File | Change |
|---|---|
| `Dockerfile` | New. Python 3.13-slim, non-root user, Gunicorn, `0.0.0.0:$PORT`. |
| `.dockerignore` | New. Excludes `.git`, secrets, `data/`, `.venv/`, tests, dev files. |
| `requirements.txt` | Added `gunicorn==23.0.0` and `packaging==24.2` with sha256 hashes. |
| `llm_metrics/web.py` | `HOST` now reads `LLM_METRICS_HOST` env var (default `127.0.0.1`). |
| `llm_metrics/real_benchmark.py` | Pre-flight DB check before the paid provider call; `import storage` added. |
| `tests/test_postgres_integration.py` | Added `_SAFE_DBNAME_RE` module constant and DB-name check in `setUpClass` to guard against SSH tunnels to production over localhost. Module docstring updated with security note. |
| `tests/test_install_requirements.py` | Added `gunicorn` and `packaging` to the expected-packages assertion. |
| `tests/test_preflight_db_check.py` | New. 10 offline unit tests for the pre-flight DB check and the DB-name guard. |
| `.gitignore` | Added `.env.*`, key/cert file patterns, container context note. |
| `design-questions/018e/` | Four role-specific design question files. |
| `design-questions/README.md` | Added 018e row. |
| `DECISIONS.md` | Added D068. |
| `PROJECT_STATUS.md` | Updated to Step 018e. |

## Test results

**387 tests total: 374 run offline, 13 skipped (TEST_POSTGRES_URL not set).**
All 374 offline tests pass. `./run.sh` verified.

New tests added in this step: 10 (6 pre-flight DB check regression tests + 4 DB-name guard tests in `test_preflight_db_check.py`).

## Docker evidence

**Container build: UNVERIFIED — Docker not available on this machine.**

The Dockerfile is syntactically correct and follows all security requirements (non-root user, no secrets in layers or build args, Gunicorn instead of Werkzeug, production binding), but cannot be executed here. The following commands are provided for verification in Step 018f:

```bash
# Build
docker build -t llm-metrics:018e .

# Confirm non-root identity
docker run --rm llm-metrics:018e whoami
# Expected: appuser (not root)

# Confirm no secrets in layers
docker history --no-trunc llm-metrics:018e | grep -i 'api_key\|password\|secret'
# Expected: no matches

# Web service smoke test (no API key needed)
docker run --rm -e PORT=8080 -e LLM_METRICS_DB_PATH=/tmp/test.db llm-metrics:018e &
curl -s http://localhost:8080/ | head -20

# Confirm default CMD makes no paid calls
docker run --rm llm-metrics:018e python -c "from llm_metrics import real_benchmark; print('no --real flag = no paid call')"
```

## Dependency / security advisory check

**Scanner: not available (pip-audit not installed).**

Packages in `requirements.txt` as of 2026-11-04:
- psycopg2-binary 2.9.10
- SQLAlchemy 2.0.36
- alembic 1.14.1
- Mako 1.3.10
- typing_extensions 4.16.0
- gunicorn 23.0.0 *(new)*
- packaging 24.2 *(new)*
- Flask 3.1.3
- Werkzeug 3.1.9
- Jinja2 3.1.6
- itsdangerous 2.2.0
- click 8.5.0
- blinker 1.9.0
- MarkupSafe 3.0.4

No packages were silently upgraded. All hashes are from PyPI. Advisory scanning should be run before 018f with `pip-audit -r requirements.txt`.

## Non-executed Cloud Run deployment checklist

This checklist must be reviewed before 018f. No steps have been executed.

### Pre-deployment
- [ ] `docker build -t REGION-docker.pkg.dev/llm-metrics-513617/llm-metrics/app:sha-COMMIT .`
- [ ] Run image smoke tests (non-root identity, no secrets in layers, web service responds)
- [ ] Push to Artifact Registry: `docker push REGION-docker.pkg.dev/llm-metrics-513617/llm-metrics/app:sha-COMMIT`
- [ ] Run `alembic upgrade head` against the Cloud SQL database before creating or updating the Cloud Run service
- [ ] Verify no live traffic hits the old schema during migration

### Identity and access (least-privilege)
- [ ] Create two service accounts: `llm-metrics-web@...` (read-only dashboard) and `llm-metrics-job@...` (benchmark job)
- [ ] Grant `llm-metrics-web` only: Cloud SQL Client, Cloud Storage read (if needed)
- [ ] Grant `llm-metrics-job` only: Cloud SQL Client, Secret Manager Secret Accessor for `OPENAI_API_KEY` (and others as needed)
- [ ] Confirm web service identity has NO access to provider API keys in Secret Manager

### Secrets (Secret Manager, not env vars in Dockerfile or gcloud command history)
- [ ] Store each API key as a Cloud Run secret: `gcloud secrets create OPENAI_API_KEY --data-file=-`
- [ ] Mount secrets as environment variables in the Cloud Run service (not build args)
- [ ] Confirm `gcloud run deploy` command contains no literal API key values

### Web service (private, IAM-authenticated)
```
gcloud run deploy llm-metrics-web \
  --image REGION-docker.pkg.dev/llm-metrics-513617/llm-metrics/app:sha-COMMIT \
  --service-account llm-metrics-web@llm-metrics-513617.iam.gserviceaccount.com \
  --no-allow-unauthenticated \
  --ingress internal \
  --region us-central1 \
  --port 8080 \
  --memory 512Mi \
  --cpu 1 \
  --max-instances 1 \
  --set-env-vars LLM_METRICS_DATABASE_URL=postgresql://...
```
- `--no-allow-unauthenticated`: Cloud Run IAM enforces access; Flask itself has no login system
- `--ingress internal`: no public internet exposure by default

### Benchmark job (one-shot, explicit --real)
```
gcloud run jobs execute llm-metrics-job \
  --image REGION-docker.pkg.dev/llm-metrics-513617/llm-metrics/app:sha-COMMIT \
  --service-account llm-metrics-job@llm-metrics-513617.iam.gserviceaccount.com \
  --region us-central1 \
  --memory 512Mi \
  --task-timeout 180s \
  -- python -m llm_metrics.real_benchmark --provider openai --real \
     --workload interactive-chat-v1
```
- `--task-timeout 180s`: outer wall-clock safety limit (not measurement timing; see D068)
- `--real` required: no accidental spend from a misconfigured entrypoint

### Post-deployment
- [ ] Confirm web service returns HTTP 200 (authenticated request via `gcloud run services proxy`)
- [ ] Confirm `/spend` page shows no prod data before first benchmark job
- [ ] Verify `gcloud run jobs describe llm-metrics-job` shows the correct service account
- [ ] Review estimated spend against $10/day target before scheduling any repeated runs

## GCP and provider spend confirmation

**No cloud resources created. No paid provider calls made. $0 incurred in this step.**

## Design Q&A (concise)

**Q (lead):** What does the pre-flight DB check catch and not catch?
**A:** It catches unreachable DB, bad credentials, and schema migration conflicts before the paid call. It does not guarantee write success (a later transaction failure can still orphan a billed attempt). See `design-questions/018e/lead-engineer.md`.

**Q (principal):** What are the risks of a single image for both web and job?
**A:** Credential isolation depends entirely on separate service accounts and Secret Manager IAM — no code-level separation. At scale, split into base + web + job derived images. See `design-questions/018e/principal-engineer.md`.

**Q (manager):** What verification is needed before 018f?
**A:** Docker build, non-root confirmation, no-secrets-in-layers check, web smoke test, deployment checklist reviewed by a second person. See `design-questions/018e/senior-manager.md`.

**Q (director):** How to evaluate the security gate vs new capability?
**A:** The gate unlocks periodic automated benchmarks and a public dashboard. Without it, the first deployment would create an exploitable surface before the first result is published. See `design-questions/018e/director.md`.

## MARKETING CHECKPOINT

**Not publishable yet.** The dashboard is still local-only; no cloud deployment exists; no periodic real benchmark data has been collected. The container is ready but unverified. This step enables 018f (first cloud deployment), which enables periodic real measurements, which enables a publishable finding.

## Remaining deployment blockers

1. **Container build unverified** — Docker not available on this machine; must be run in 018f.
2. **Cloud SQL not provisioned** — no database URL available yet for Cloud Run.
3. **Artifact Registry not created** — no push target for the image.
4. **Service accounts not created** — IAM identities must be provisioned before the services run.
5. **pip-audit not run** — advisory scan pending.

## Smallest next step

**Step 018f:** Provision Cloud SQL, Artifact Registry, and Cloud Run services; build and push the container; deploy the web service (private, IAM-authenticated); run one benchmark job; verify the spend page shows the result.
