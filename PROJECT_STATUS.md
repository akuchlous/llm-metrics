# Project status

_Last updated: Step 027c per-request pilot charts (local preview, not deployed) and plan-only pilot restart; awaiting review; Approval B not started; Step 023 PARTIAL — 2026-11-07_

## Current state

**Step 027c complete locally, not deployed; awaiting local visual review and ChatGPT review.**
- Metric page charts of every real pilot request over time (TTFT, total response time, tokens/s) and every slot's outcome, from a sanitized per-slot series (D089). Preview with `./run.sh site-preview`; deploy to staging only after you say "deploy staging".
- `./run.sh pilot-plan --start <UTC>` plans (only) a new 24-hour run; launching needs Approval C after the original pilot is stopped and audited.
- Every page heading is now a question (D090). 690 tests OK (7 skipped).

**Local website preview added (D088), awaiting ChatGPT review.** `./run.sh site-preview` builds the staging-equivalent site locally and serves it on http://localhost:8000 (Ctrl+C to stop; `--help`, `--drafts`, `--analytics`, `--port`). No deploy, no cloud calls. Local preview and human review now come before every Cloudflare staging deploy. 670 tests OK (7 skipped).

**Step 027b complete (provisional), staging updated, awaiting ChatGPT review.**
- `/openai-ttft` and `/metrics/openai/ttft` on staging show real pilot data: "Partial pilot, as of 2026-11-07 15:30:00 UTC". 86 due slots: 85 successes, 1 provider error, 0 missing. TTFT p50 1,637 ms, p95 2,551 ms; total p50 4,279 ms; 116.7 tokens/s; success 98.8%. See `prompts/027b-output.md`, D087.
- Staging Worker version 4843a1e5. 664 tests OK (6 skipped).
- After 18:00Z the scheduler and key stay attached until the documented `stop`, which needs separate approval.

**Step 027a complete, staging updated, awaiting ChatGPT review.**
- Question-first home page (newest first, 50 per page, `/page/N` only when needed), categories, answer-first question pages, related questions, metric question `/openai-ttft` with no numbers, simpler stylesheet. See `prompts/027a-output.md`, D086.
- Four new educational drafts (not approved, not on staging); duplicate-calls article still a draft.
- Approved follow-up question `/useful-llm-api-metrics` ("Which LLM API metrics are useful, and why?"), live on staging.
- Staging Worker version 7e8681e8 at https://llmxchange.akuchlous.workers.dev; 656 tests OK (6 skipped).

**Step 027 complete; staging deployed (Approval A, D085) and updated in Step 027a. Production not deployed.**
- **Design:** an "LLM Xchange" brand with top navigation (Questions, Metrics, Project Costs, Methodology), cards and a responsive dark-mode stylesheet. No JavaScript or trackers.
- **Costs:** `/costs` is built from a private reviewed ledger (`cost_ledger.py`). It shows actual charges only, and "Full lifetime total not yet verified." until every source is reconciled.
- **Hosting:**
  - Generated `sitemap.xml`, `robots.txt`, `_redirects`, `_headers` and `404.html`.
  - A `wrangler.jsonc` for Cloudflare Workers Static Assets (`drop-trailing-slash`, `404-page`).
  - An offline host-routing emulator and a forbidden-content scan.
- **Release lanes:** `publish_runner` runs separate editorial and metrics lanes, with a cadence config and an emergency switch.
- **Deferred decisions (ChatGPT review of 026):**
  - `/costs`, pricing Q&A foundations and the ledger format: done in 027.
  - **Step 028** must deliver immutable dated metric snapshots, sample-size thresholds and the weekly metrics Q&A workflow **before any real benchmark result is published**.
- **Tests:** Docker `./run.sh test` (see 027 output).
- **Not done:** no screenshots (the headless browser image was not permitted).
- **Cloudflare status (2026-11-07): staging deployed (Approval A).**
  - https://llmxchange.akuchlous.workers.dev: one assets-only Worker `llmxchange` (version 4843a1e5, after 7e8681e8, a46f81ef and the first deploy 34fc2545), workers.dev only, preview URLs off, no custom domain, routes or DNS. Built with `--staging`: approved answers only, no dated editions, nothing archived, `noindex, nofollow` everywhere.
  - Live routing, redirects, 404s, security headers, robots and content checks passed; see `prompts/027-output.md`. Screenshots/Lighthouse not run (headless browser not permitted).
  - Wrangler 4.152.0 via OAuth login; Cloudflare agent plugin installed. `llmxchange.com` not purchased; production (Approval B) not started.
- **No GCP, DNS or paid Cloudflare actions.**

**Step 026 complete (local only), awaiting ChatGPT review: question registry and immutable dated Q&A editions.**
- **Registry:** each question directory has a `question.json` (opaque `question_id`, stable path, editions). Editions reuse the Step 025 `page.json` and fragments, with `status` draft/approved.
- **Publishing:**
  - `--publish-at` freezes approved editions into `site_content/archive/` at `/reports/<UTC date>/<slug>[/rN]`, recorded in manifest `llm-metrics.publication.v1`.
  - Archived bytes are served verbatim; any modification is refused.
- **Pages:** home feed (newest first), `/questions` directory, and stable question pages with edition history. Editions are canonical to the stable page. A `redirects.json` plan is produced.
- **Indexing:** the empty metric page is `noindex`.
- **Content:**
  - New draft article "How do we prevent duplicate paid LLM API calls in scheduled benchmarks?", with facts tested against the code.
  - The TTFT article edition is approved.
  - **Nothing is published yet** (the archive is empty).
- **Tests:** 27 new; Docker `./run.sh test`: 622 tests, 5 skipped, 0 failures.
- **Deferred:** dated metric snapshots and sample thresholds (D083).
- **No hosting, DNS or cloud changes.**

**Step 025 complete (local only), awaiting ChatGPT review: first static question and metric pages.**
- **Command:** new `llm_metrics.static_site` (`--output DIR --site-url https://llmxchange.com [--analytics F --data-source real|synthetic] [--report R]`).
- **Pages built:** `/`, the `/llm-performance` hub, the Q&A article `/how-to-measure-openai-ttft` and the metric page `/metrics/openai/ttft`, cross-linked. It uses Jinja2 (no Flask, SQL or GCS).
- **Content and data:**
  - Editorial text is in `llm_metrics/site_content/`, with an explicit `answer_revision`.
  - Numbers come only from a validated canonical `llm-metrics.analytics.v1` summary.
  - Without a dataset, the pages show an explicit no-data state. Synthetic data is bannered and `noindex`.
- **SEO and checks:** canonical, OG, breadcrumbs equal to `BreadcrumbList`, `Article` JSON-LD with no invented dates/authors/image, a meta CSP, and build-time checks. There is also an advisory Yoast-inspired editorial report.
- **Tests:** 31 new tests; the D056 import guard was narrowed (D082). Docker `./run.sh test`: 595 tests, 5 skipped, 0 failures.
- **Not done:** nothing hosted, no DNS or cloud changes, no real dataset rendered.

**Step 024 complete (offline only), awaiting ChatGPT review: read-only analytics from immutable GCS records.**
- **Command:** new `llm_metrics.record_analytics` (`python -m llm_metrics.record_analytics --input MIRROR --output FILE ...`). It reads a local mirror's `<prefix>/v1/requests/prod/` only.
- **Population:** exact provider, model, profile, workload, origin and UTC `[start, end)`.
- **Output:** a canonical, create-only `llm-metrics.analytics.v1` summary containing:
  - reliability over all attempts
  - success-only nearest-rank p50/p95, min, max and latest for TTFT, total latency and throughput
  - known cost and tokens, with failed attempts counted as cost-unknown
  - per-record SHA-256 evidence and a manifest hash
  - machine-readable caveats
- **Slot completeness** is reported only with `--collector-policy-start`, via `collector_audit` over the claims in the mirror; otherwise it is null.
- **Fail-closed:** invalid, misplaced, symlinked or oversized input, duplicates, mixed populations, inconsistent slot evidence or zero rows exit 1 with nothing written.
- **Tests:** 31 new tests on committed synthetic fixtures (`tests/fixtures/gcs_mirror/`, generated by `tests/analytics_fixtures.py`). Docker `./run.sh test`: 564 tests, 5 skipped, 0 failures.
- **No cloud, provider or paid actions.** The Step 023 collector, scheduler, credentials and policy are untouched. The real pilot mirror has **not** been analysed yet.

**Progress 2026-11-07T09:31Z:** 63 of 63 begun slots claimed and recorded (the 09:30Z slot completed at 09:32Z, after the audit snapshot). 62 successes and 1 recorded `provider_error` (21:30Z), with 0 claims without a record, 0 duplicates, 0 late starts and 0 failed executions. TTFT p50 1649 ms, total latency p50 4293 ms, 115 tokens/s p50. Model cost so far $0.0200. Window ends 2026-11-07T18:00Z; indefinite collection not enabled.

**Step 023 PARTIAL — bounded 15-minute OpenAI collector deployed and ACTIVE; 24-hour results pending.**
- **Code:**
  - New `llm_metrics.scheduled_collector`. It takes no arguments and has a fixed scope: `openai.gpt-6-luna.v1` / `interactive-chat-v1` / gcp / GCS.
  - **Policy:** from the job env, a UTC quarter-hour start and exactly 24 h, so exactly 96 slots.
  - **Per-slot gate:** an atomic create-only GCS claim per slot, read back and checked against GCS server time; a 7-minute late limit; expiry rechecked before the call. Duplicates skip, ambiguous claims refuse, a claimed slot is never retried, and the claim's attempt id is the record id.
  - **Other:** a dry-run mode; structured sanitized events; a read-only `llm_metrics.collector_audit`.
  - The one-off GCS and SQL paths and the 018h guard are unchanged.
  - Docker `./run.sh test`: 533 tests, 5 skipped, 0 failures.
- **Cloud (Approval A, then Approval B):**
  - Dedicated job `llm-metrics-collector` @ `sha256:5fb1a383…` (SA `llm-metrics-collector@`, the only account able to read `OPENAI_API_KEY`; `llm-metrics-job@` lost that access).
  - Scheduler `llm-metrics-collector-15m` (`*/15`, Etc/UTC, retry 0); its SA has `run.invoker` on that job only.
  - A preflight-only 7-day lifecycle rule.
  - Email alerts: collector ERROR / failed task, scheduler failure, and missed runs (33 min).
  - Phase A dry runs passed; one late-start refusal was a correct gate action.
- **Pilot window:** **2026-11-06T18:00Z → 2026-11-07T18:00Z** (≤ 96 paid requests, ≤ about $0.30/day).
- **First scheduled slot:** verified: `prod` record `f2a304348de94d86a4afdf4e76ed6271` (TTFT 2087 ms, latency 4941 ms, $0.0003295), audit clean.
- **Credential state:** the OpenAI key reference is attached to the collector job and stays attached after expiry until `scripts/gcp/023_collector.sh stop` is run. The code refuses after expiry regardless.
- **Post-window:** run `audit 2026-11-06T18:00:00Z`, then `stop`.
- **Evidence:** `prompts/023-output.md`. MARKETING: not publishable.

**Step 022 complete: first live GCS-backed OpenAI measurement.**
- **Code:**
  - `LLM_METRICS_RESULTS_BACKEND` (`sql` default, `gcs` explicit).
  - `benchmark.measure_attempt` split out of `run_attempt`.
  - `real_benchmark` GCS mode: gcp origin and OpenAI only; configuration checks before the key or adapter; a real create/read/no-overwrite storage preflight before the paid request; the attempt id fixed before the request; exit 3 if the record is not confirmed durable; no provider retry.
  - New `llm_metrics.gcs_smoke`: storage only, refuses if any provider key is present.
  - The SQL path and the 018h guard are unchanged.
  - Docker `./run.sh test`: 511 tests, 5 skipped, 0 failures, PostgreSQL integration executed.
- **Cloud (two in-session approvals):**
  - New private bucket `gs://llm-metrics-513617-results` (UBLA, PAP enforced); the job service account has objectCreator + objectViewer on it only.
  - Image `sha-ee33635` deployed by digest `sha256:3da244ac…`.
  - Phase A: a storage smoke as the job service account, with no key, wrote a synthetic `test` record and verified replay and conflict behaviour; the operator re-downloaded it and the SHA-256 matched.
  - Phase B: one paid execution (`fvv5b`) produced `prod` record `attempts/v1/requests/prod/2026-11-06/e00ee56c46ba499b8579ba3413611be3.json` (sha256 `75e6986d…`, independently verified): TTFT 1913.4 ms, total latency 5314.0 ms, 88.3 tokens/s, 1795 input / 0 cached / 300 output tokens, $0.0003295, request `req_06166e6d…`.
  - The key was detached immediately afterwards.
- **Current state:**
  - The job is idle on the digest with no secrets, no database and no schedule.
  - No Cloud SQL.
  - Backups unchanged.
- **Spend and open risk:** under $0.01. The crash window between the paid response and the write remains open.
- **Evidence:** `prompts/022-output.md`. MARKETING: not publishable (n = 3).

**Step 021 complete (offline only): immutable per-attempt GCS records.**
- **What it adds:** `llm_metrics/object_results.py` defines schema `llm-metrics.attempt.v1`, one canonical JSON object per attempt.
  - **Contents:** the 20 non-identity request facts plus the observations; unknown values are `null`, never 0. Prompts, responses, diagnostics and secrets are excluded by construction.
  - **Object name:** `<prefix>/v1/requests/<env>/<UTC date>/<attempt_id>.json`.
  - **Writer:** create-only GCS writes (`ifGenerationMatch=0` plus content MD5, client retries off). An identical replay succeeds; a conflicting payload is refused, never overwritten. A lost acknowledgement is reconciled by byte comparison. Storage retries are bounded (3 attempts).
  - **Read path:** a validated reader, plus an exact mapping to and from the SQL rows.
- **Dependencies:** `google-cloud-storage` 3.17.1 plus its 19 transitive dependencies were added hash-pinned. The production image grows by about 69 MB; it was not deployed.
- **Untouched:** the module is **not** wired into `run_attempt`, `real_benchmark` or the 018h guard (a test enforces this). Cloud collection still requires PostgreSQL.
- **Tests:** 43 new offline tests (fake store, plus the real GCS client over a fake HTTP session). Docker `./run.sh test` passed twice: 487 tests, 5 skipped, 0 failures, PostgreSQL integration executed.
- **Cloud:** no GCP changes and no paid calls. The cloud job is still idle and credential-less.
- **Evidence:** full details in `prompts/021-output.md`. MARKETING: not publishable (n = 2).

**Step 020 complete: guarded second OpenAI cloud pilot.** Two in-session approvals. **Phase A:** the `OPENAI_API_KEY` reference was detached from Cloud Run Job `llm-metrics-benchmark` first; the production image was built by Cloud Build (new `cloudbuild.yaml`, least-privilege `llm-metrics-build` SA) from `0ce36df` (application code = validated `644870c`) and deployed **by digest** `sha256:1b67b96f…a575` (1 task, 0 retries, 180 s, explicit `--workload interactive-chat-v1`); one negative execution (`q9nlr`) exited 2 with the 018h guard message "…require an explicit PostgreSQL… No request was made." **Phase B:** temporary `llm-metrics-pg-020` (PG17 Enterprise `db-f1-micro`, zonal, no backups, zero authorized networks) migrated to Alembic head with 0 rows; one paid execution (`4mwqz`) succeeded: attempt `13caf417…`, provider request `req_d382c497…`, TTFT 2469.9 ms, total latency 5343.4 ms, 105.3 tokens/s, 1795 input / 0 cached / 300 output (cap), $0.0003295, 4 observations. Exported to `gs://llm-metrics-513617-pilot-backups/snapshots/020/2026-11-06-llm-metrics-benchmark-4mwqz/` (CSV + manifest + SHA256SUMS), independently re-downloaded and verified, and test-restored into local PostgreSQL. Then key/DB refs removed from the job, instance (no backups) and DB secret deleted. **Current cloud state:** job on guarded digest with no credentials/DB/schedule; no Cloud SQL; secret `OPENAI_API_KEY` only; ongoing cost ≈ $0/month; Step 020 spend < $0.01. Cloud commands ran from the local machine via a newly installed `gcloud` (not Cloud Shell; D077). Docker `./run.sh test`: 444 tests, 5 skipped, 0 failures. Full evidence in `prompts/020-output.md`. MARKETING: not publishable (n = 2).

**Step 019.2 complete: setup.sh hardening + Docker Compose verification.** Six issues in `setup.sh` resolved: (1) installation functions fail-fast via subshell `set -e` — no partial-success path; (2) DNF repo URL is per-distro (`download.docker.com/linux/fedora/` for Fedora, `.../rhel/` for RHEL/CentOS/Rocky/Alma); (3) docker group add now prints explicit root-equivalent security warning and requires typing 'yes'; (4) new Compose-only install path when Docker present but Compose v2 missing; (5) `VERSION_CODENAME` validated against known-supported Docker apt releases; (6) `main()` guarded by `BASH_SOURCE` check so script is sourceable from tests. Four new focused tests added (10 in `SetupScriptTest`, 7 in `RunScriptTest`). `compose.yaml` fixed: `COMPOSE_MODE` now forwarded to the container so `./run.sh test` auto-exits instead of staying in serve mode. **Docker Compose verification (cycle 1): `./run.sh test` — 444 tests, 5 skipped, 0 failures; PostgreSQL integration tests executed (not skipped); dashboard smoke test HTTP 200; containers and `db_data` volume removed via EXIT trap.** Full evidence in `prompts/019.2-output.md`.

**Step 019 complete: one-command disposable Docker local workflow.** `./run.sh` now requires Docker and `docker compose`; native Python path removed. `compose.yaml` starts a `postgres:17-alpine` service (named volume, no host port exposure) and an `app` service built from the new `Dockerfile.dev` (includes `tests/`). `docker/entrypoint.sh` runs all tests (offline + PostgreSQL integration via `LLM_METRICS_COMPOSE_RUN=1`), seeds simulated history, runs one measurement, then serves the dashboard (serve mode) or runs an HTTP smoke test and exits (test mode). `compose down -v` on EXIT trap cleans project-scoped containers, network, and volume. `tests/test_postgres_integration.py`: `setUpClass` now accepts Compose service DNS hostnames when `LLM_METRICS_COMPOSE_RUN=1`; `tearDownClass` is a no-op in Compose mode (volume handles cleanup). Added `PostgresGuardTest` (7 offline safety tests). `tests/test_run_script.py` rewritten: 6 tests for Docker prerequisite errors, usage errors, and valid modes. Full offline suite: 433 tests, 13 skipped (PostgreSQL integration — run inside Compose), 0 failures. **Docker runtime verification: UNVERIFIED** — Docker unavailable on this machine; verification requires Cloud Shell (see `prompts/019-output.md`). No GCP changes; no paid calls. Full evidence in `prompts/019-output.md`.

**Step 018h complete: fail-closed paid cloud execution guard and durable-store decision.** `real_benchmark.run()` now rejects any non-local-origin paid benchmark attempt that lacks an explicitly configured PostgreSQL `LLM_METRICS_DATABASE_URL`, preventing silent data loss to ephemeral container SQLite. Guard fires before the API key is read or any provider adapter is constructed; local-origin SQLite behavior is unchanged. 31 new regression tests (all passing); `test_origin_comes_from_the_environment` updated to supply a fake PostgreSQL URL and patch `storage.connect`. Full suite: 423 tests (379 offline, 44 new + existing, 13 skipped). Storage analysis (D073): Cloud SQL per-session is recommended; Cloud Storage requires a new backend; serverless SQL unconfirmed on GCP. **Operational caveat (resolved in Step 020):** the job now runs the guarded digest `sha256:1b67b96f…`; `app:sha-9cf8ac9` is retained only as a rollback reference and must not be executed. No GCP changes; no paid calls. Full evidence in `prompts/018h-output.md`.

**Step 018g complete: post-pilot security cleanup and durable backup.** All five 018f findings resolved in Cloud Shell after explicit approval: (1) project `roles/editor` removed from the default compute service account (unused by the job, build or any service); (2) Cloud Run Job's `LLM_METRICS_DATABASE_URL` reference and Cloud SQL attachment removed, secret deleted; (3) `OPENAI_API_KEY` v1 disabled (v2 enabled, job uses `latest`); (4) pilot CSVs (1 request, 4 observations) backed up to private, versioned `gs://llm-metrics-513617-pilot-backups/snapshots/018f/2026-11-04/` with a `SHA256SUMS` manifest, verified by independent download (D072); (5) three orphaned Cloud Build source tarballs deleted; image `app:sha-9cf8ac9` retained. Residual risk: without a DB URL the job falls back to container SQLite, so a manual execution would spend ~$0.0003 and lose the result; do not execute the job until a fail-closed guard (proposed 018h) or a database exists. Remaining GCP resources: idle Cloud Run Job, `OPENAI_API_KEY` secret, Artifact Registry image, backup bucket, empty Cloud Build bucket, service accounts, budget alert. Ongoing cost ~$0.13/month. No code changes; tests not re-run (inherited 018e result). Full evidence in `prompts/018g-output.md`.

**Step 018f complete: first real OpenAI Cloud Run measurement verified.** One `gpt-6-luna` / `interactive-chat-v1` request executed from a Cloud Run Job in gcp/us-central1; stored in Cloud SQL; Cloud SQL immediately deleted post-run. TTFT 2013ms, total latency 4428ms, 128 tokens/s, 1795 input / 300 output tokens (hit cap), $0.00033. Total Stage B spend: under $0.05. Full evidence in `prompts/018f-output.md`. GCP resources still running: Artifact Registry image (free tier), Cloud Run Job (free idle), `OPENAI_API_KEY` secret (~$0.06/month), `llm-metrics-job` and `llm-metrics-build` service accounts (free), budget alert. Ongoing cost: ~$0.14/month. Data CSV preserved at `~/llm-metrics-018f-result/` in Cloud Shell persistent home. Docker build verified in Cloud Shell (Cloud Build path; local daemon cannot push to Artifact Registry — D071).

**Step 018e implemented (pending review): secure Cloud Run deployment readiness (code only).** `Dockerfile` added: Python 3.13-slim, non-root `appuser`, Gunicorn (`--workers 1 --timeout 120`), `0.0.0.0:${PORT}` binding for Cloud Run. `.dockerignore` excludes `.git`, secrets, `data/`, `.venv/`, tests, and dev files. `gunicorn==23.0.0` and `packaging==24.2` added to `requirements.txt` with sha256 hashes. `web.py HOST` reads `LLM_METRICS_HOST` env var (default `127.0.0.1`; `./run.sh` unaffected). `real_benchmark.run()` pre-flight DB check before the paid call: `storage.connect()` failure returns exit 2 with a redacted URL. `test_postgres_integration.py` strengthened with database-name disposability check (`_SAFE_DBNAME_RE`) guarding against SSH tunnels to production over localhost. `.gitignore` expanded with `.env.*`, key/cert patterns. 387 tests total (374 run offline, 13 skipped); `./run.sh` verified. Container build: **unverified** (Docker not available). Advisory scan: **not scanned**. No GCP resources created; no paid calls.

**Step 018d implemented (pending review): real PostgreSQL integration proof and safe migration gate.** 13 integration tests run against PostgreSQL 17 (local, disposable `llm_metrics_018d` database): v7 schema creation, FK/index presence, revision row, request/observation round-trip, failed-request NULL semantics, CHECK and FK constraint enforcement, atomic rollback, environment isolation, cache-policy filtering, spend aggregation, seeding idempotency, reconnect durability, and timestamp ordering all pass. Fail-closed: PostgreSQL with existing tables but no Alembic revision now raises `RuntimeError` instead of silently stamping. Credentials kept out of Alembic config strings (connection passed via `config.attributes["connection"]`); `_redact_db_url()` utility strips `user:pass@` from URL strings. `spend_by_model` ORDER BY fixed for PostgreSQL strict GROUP BY (`r.c.total_cost.is_(None)` → aggregate expression). 376 tests total (363 run offline; 13 integration skipped without `TEST_POSTGRES_URL`); `./run.sh` verified. No GCP resources created.

**Step 018c implemented: PostgreSQL-ready storage connection and dialect correctness.** `LLM_METRICS_DATABASE_URL` env var (sqlite or postgresql only) selects the database; falls back to `sqlite:///` + `LLM_METRICS_DB_PATH`. Engine cache is now keyed by URL string. `connect()` accepts `pathlib.Path | str`. `_ensure_schema()` skips SQLite-specific PRAGMAs and the legacy v0–v7 bridge for PostgreSQL. `save_new_observations()` dispatches to `_sqlite_insert` or `_pg_insert` based on dialect. `_observations.request_id` FK added to Table metadata to match the Alembic baseline. `psycopg2-binary==2.9.10` pinned in requirements.txt. New `config.get_database_url()` function. 359 tests pass; PostgreSQL integration not yet verified (no live server; dialect compilation tests added).

**Step 018b implemented: SQLAlchemy Core + Alembic persistence portability.** Storage layer rewrites from `sqlite3` to SQLAlchemy Core + Alembic; engine cache, legacy v0→v7 upgrade bridge, fresh-DB path all working. 347 tests pass; `./run.sh` verified.

**Step 017 implemented: codebase simplification and reuse.** A behavior-preserving cleanup. LiteLLM was evaluated against the Step 016 contract and not adopted (D065): it fetches a price map over the network on import, records zero usage when a provider reports none, routes Gemini and xAI through different endpoints than our request profiles, and had compromised PyPI releases in March 2026. The four direct adapters now share `http_streaming.status_failure`, `checked_usage` and `StreamContext` instead of four copies. `real_smoke` delegates to `real_benchmark.run`, and the test fakes live in `tests/fakes.py`. SQLAlchemy Core + Alembic are recommended for the Google Cloud persistence step, not adopted now (D066). Package Python fell from 5,737 to about 5,590 lines; dependencies, wire requests, profiles, stored facts, pages and API are unchanged.

**Step 016 implemented (pending review): four-provider benchmark adapters.** One real target per provider, each defined by a versioned request profile in `llm_metrics/targets.py` and stored with every attempt (`requests.request_profile_id`, schema v7): OpenAI `gpt-6-luna` (`openai.gpt-6-luna.v1`), Anthropic `claude-haiku-5-5` (`anthropic.claude-haiku-5-5.v1`), Google `gemini-3.5-flash-lite` (`google.gemini-3.5-flash-lite.v1`), xAI `grok-4.20-0309-non-reasoning` (`xai.grok-4.20-0309-non-reasoning.v1`). New standard-library adapters (`anthropic_provider`, `google_provider`, `xai_provider`) share `http_streaming` helpers with the refactored OpenAI adapter; every adapter builds its body from its profile, and `benchmark.run_attempt` refuses a provider whose model or cache policy disagrees with its registered profile. Costs price provider-reported cached input at the cached rate, and each attempt stores the cached rate (`requests.cached_input_price_per_1m`). `python -m llm_metrics.real_benchmark --provider <name> --real [--workload ID]` is the explicit one-request pilot path. Model ids, endpoints, streaming, usage, reasoning, cache controls and prices were verified against official documentation on 2026-11-01 (D062–D064, `prompts/016-output.md`). No paid or network call was made; `interactive-chat-v1` is unchanged; pages and API responses are byte-identical to Step 015.

**Step 015 complete: versioned benchmark workloads.** `llm_metrics/workloads.py` is the single, dependency-free catalogue of benchmark workloads: frozen `Workload` definitions (versioned id, category, version, name, description, prompt, output cap, approximate input-size target) built deterministically from original synthetic material. Six candidate benchmark workloads (`interactive-chat-v1` 300, `coding-v1` 1000, `rag-v1` 500, `summarization-v1` 1000, `extraction-v1` 150, `agent-tool-v1` 300 output tokens; ~2K/8K/16K/32K/4K/8K input tokens by a 4-characters-per-token estimate) plus the real smoke check `smoke.short_text.v2`. `benchmark.run_attempt(provider, workload, ...)` sends the catalogue's prompt and cap and stores its id, and refuses a workload that is not the catalogue definition of its id. `python -m llm_metrics [--workload ID]` (default `interactive-chat-v1`); `real_smoke` stays fixed to the smoke workload. No schema change; prompts are still never stored (D061).

**Step 014d complete: a small versioned read-only JSON API.** `GET /api/v1/metrics?metric=&window=` returns one aggregate metric window as JSON facts (numbers, `null` for unknown, ISO 8601 UTC times), built from the same `analytics` result as the aggregate page. It names its population (simulated dummy provider), metric and unit, and window; `samples` covers successful observations only and `reliability` every attempt. Shared query definitions (metrics, windows, populations, validation) moved from `dashboard.py` to `query.py`; the new `api.py` serializes without Flask. HTML pages are byte-identical to 014c (D060).

**Step 014c complete: analytics separated from view preparation.** New `llm_metrics/analytics.py` returns natural values (floats, ints, aware datetimes, None for unknown) for metric windows, nearest-rank summaries, success rates, recent attempts, and real-only spend; `dashboard.py` keeps query semantics and turns those facts into display text, links, and chart geometry, and no longer reads storage. Direction `web → dashboard → analytics → storage`, enforced by tests. Rendered pages are byte-identical to 014b (D059).

**Step 014b complete: presentation in Jinja templates.** `dashboard.py` no longer builds HTML: it returns view data (formatted values, "—" for unknown, link targets, chart coordinates) and `web.py` renders it with templates in `llm_metrics/templates/`; the stylesheet moved to `llm_metrics/static/dashboard.css`, so the CSP now allows only same-origin stylesheets (`style-src 'self'`, no `'unsafe-inline'`). Visible page content is unchanged apart from removing development step numbers from product copy (D058).

**Step 014a complete: Flask foundation.** The dashboard's HTTP boundary is now a small Flask application (`llm_metrics/web.py`, `create_app()` factory) in place of `http.server`; routes, query validation, page content, and status codes are unchanged. `dashboard.py` is the HTTP-free application/view layer (validation, data loading via `storage`, HTML rendering); HTML stays in Python until 014b moves it to templates. Flask is the first runtime dependency: pinned with hashes in `requirements.txt` and installed by `run.sh` (D056, D057). Nothing outside `web.py` imports Flask.

**Step 013 complete (Metrics v1 data completeness), all four parts.** Successful attempts record `output_tokens_per_s` (provider-reported output tokens over the first-to-last output chunk interval; TTFT excluded; omitted when undefined), and every new attempt records its benchmark case (`workload_id`: `simulated.default.v1` or `smoke.short_text.v2`), where the runner executed (`origin_cloud` / `origin_region` from `LLM_METRICS_ORIGIN_CLOUD` / `LLM_METRICS_ORIGIN_REGION`, default `local` / `unknown`), the requested `cache_policy` (`disabled` for the OpenAI smoke request, which sends `prompt_cache_options: {"mode": "explicit"}` with no breakpoints; `provider_default` for the simulated provider), and provider-reported `cached_input_tokens` (0 = reported zero, NULL = not reported). Schema version 6; historical rows keep workload/origin/cached tokens NULL and cache policy `unknown`. No paid call was made for this step, so the cache control has not yet been exercised against the live API.

**Step 012a complete; the Step 012 live path is validated.** Step 012 added the first real provider (OpenAI `gpt-6-luna`, Responses API, standard library only) behind the existing boundary, callable only via `python -m llm_metrics.real_smoke` (one paid call, key from `OPENAI_API_KEY`, stored as `prod`); Benchmark API Spend page; real and simulated data labelled and separated. Step 012a closes it: price $0.10 / $0.50 per 1M verified against OpenAI's official pricing documentation; `reasoning.effort: none` confirmed by the official model page; OpenAI's `x-request-id` stored per attempt as `provider_request_id` (schema version 4).

Live validation history (owner-run, 2026-10-30; **validation of the path, not benchmark results**): the first real request (`6a39b71e…`) failed as `provider_error` after 5425.6 ms, and three more early attempts were also stored as `provider_error`. Two later `--debug` runs got HTTP 200 followed by an in-stream `error`; once its nested details were read, it showed `insufficient_quota` / `credit_balance_exhausted` (the OpenAI account had no credit). Those two rows were deleted from the local database at the owner's request, and such account errors are now rejected and not recorded. The earlier failures' cause was never captured and is presumed but not confirmed to be the same. After credit was added, one request succeeded (`44c889cb…`): total latency 3880.7 ms, TTFT 3630.3 ms, 17 input / 14 output tokens (max 64), about $0.000009. One sample says nothing about typical performance.

Working:
- `./run.sh` creates/reuses `.venv`, installs the hash-pinned `requirements.txt` when it changed (network needed only then), runs tests, seeds simulated TTFT history (test only, idempotent), makes one benchmark attempt (outcome, tokens, total latency, TTFT, token and chunk throughput, cost; workload `interactive-chat-v1`), then serves the dashboard at `http://127.0.0.1:8000/` until Ctrl+C.
- `APP_ENV=test` is the safe default; `APP_ENV=prod ./run.sh` refuses to run (no implicit spend).
- `python -m llm_metrics.real_benchmark --provider openai|anthropic|google|xai --real [--workload ID] [--debug]`: exactly one real request to the one chosen benchmark target (default workload `interactive-chat-v1`), stored as `prod` with its request profile id, workload, origin, cache policy, provider-reported tokens (including cached input), provider request id, and the rates used. Requires that provider's key variable only; every refusal happens before network access. Never iterates providers.
- `python -m llm_metrics.real_smoke [--debug]`: exactly one real OpenAI `gpt-6-luna` request (requires `OPENAI_API_KEY`; refuses without it), stored with `environment = 'prod'`, workload `smoke.short_text.v2`, origin, cache policy `disabled`, OpenAI-reported cached input tokens, and OpenAI's request id; `--debug` prints sanitized failure diagnostics (never stored). Request/configuration and account-credit errors are rejected and not recorded.
- Each run saves one `requests` row (attempt) with its `outcome`, `workload_id`, `origin_cloud`, `origin_region`, `cache_policy` (all required) and `cached_input_tokens` (when reported). Success: tokens, max output tokens, prices, costs, and up to four linked observations (`total_latency`, `ttft`, `output_tokens_per_s`, `output_chunks_per_s`), in one transaction. Failure: category, `failed_after_ms`, prices and cap; tokens/costs NULL (unknown); no observations.
- `python3 -m llm_metrics.seed_history` adds 168 hourly simulated TTFT rows (2026-10-23 00:00 to 2026-10-29 23:00 UTC); re-running adds nothing.
- Dashboard (`python -m llm_metrics.web`, Flask on 127.0.0.1, debug mode always off; `/?window=24h|7d|30d&metric=total_latency|ttft|output_tokens_per_s|output_chunks_per_s`): `TEST / SIMULATED DATA` label, metric and window links, observed benchmark success rate over all attempts in the window (count, rate, failures by category; no attempts → no rate), then for successful attempts only: latest value, nearest-rank p50/p95/p99 with `n` (in the metric's unit), and an SVG chart spanning the window, all from the same `test`/dummy/<metric> rows with `now − window <= recorded_at <= now`. Invalid or repeated `window`/`metric` → HTTP 400. Standard library only; no JavaScript.
- Recent requests view (`/requests`): the 20 most recent attempts with outcome (FAILED + category), tokens, total latency (primary), TTFT, token throughput (before chunk throughput), chunk throughput, costs, failed-after time, provider / model, workload, and origin; unknown values shown as "—"; labelled simulated or real.
- Benchmark API Spend (`/spend?window=`, default 30d, real data only): per provider/model successful paid calls, tokens, known total cost, failed attempts (cost unknown), and a grand total.
- Pages are labelled TEST / SIMULATED DATA or REAL PROVIDER DATA; `/requests?data=simulated|real` switches population.
- JSON API (`/api/v1/metrics?metric=&window=`, same values and defaults as the aggregate page): `api_version`, `population` (`data: "simulated"`, provider, model), `metric` (name, unit), `window` (name, ISO start/end), `samples` (successful observations: count, first/latest time, latest value, p50/p95/p99, `null` when none), `reliability` (all attempts: counts, rates `null` when none, failures by category). 400/404/405/500 under `/api/` are JSON errors that never echo input. Field meanings and types are the v1 compatibility contract (README, D060).
- `python -m llm_metrics --workload <id>` runs any catalogue workload against the simulated provider; an unknown id is refused (exit 2, valid ids listed, input not echoed) before anything is measured.
- 359 `unittest` tests (pass on Python 3.13 in the project venv); none reach external networks (two web tests serve on 127.0.0.1). Web routes are tested with Flask's test client; page tests render the real templates.
- One runtime dependency, Flask (with its libraries), used only by `web.py`. Provider network access and secrets are used only by `real_smoke` and `real_benchmark`.
- All Python follows the Google Python Style Guide (D055): `pyink` formatting, isort `google` import order, and Google's `pylintrc` report no findings. These tools are optional development tools, not dependencies.

Data from `./run.sh` is **simulated** and does not represent real LLM performance. Real data exists only after `real_smoke` or `real_benchmark` is run.

## Run

Requires Linux/Chromebook Linux and Docker with Compose v2.  Run `./setup.sh`
to install Docker if needed.

```bash
git clone https://github.com/akuchlous/llm-metrics.git
cd llm-metrics
./run.sh          # full workflow: tests → seed → measure → dashboard
./run.sh test     # same, plus HTTP smoke test, then auto-exits
```

The runtime and test suite run entirely inside Docker Compose — no host Python
or `.venv` required.  Container and volume are removed automatically on exit.

`LLM_METRICS_PORT` changes the dashboard port (default `8000`, `0` = any free port).

## Architecture

```text
run.sh             venv -> dependencies -> tests -> seed (test) -> measurement -> dashboard
requirements.txt   Flask and its libraries, pinned with sha256 hashes
scripts/install_requirements.py  hash-checked install; pinned, verified pip zipapp when the venv has no pip
llm_metrics/
  outcomes.py      outcome/failure categories + success_rate
  providers.py     provider interface (text chunks + final Usage, ProviderFailure); DummyProvider with simulated tokenizer, output cap, deterministic failures
  targets.py       benchmark targets: versioned RequestProfile per provider/model (settings, reasoning, cache policy, key variable); imports nothing from llm_metrics
  http_streaming.py  shared adapter HTTP behavior: one request without retry, status mapping, usage validation, StreamContext (failure identification, read errors), SSE parsing, sanitizing, RequestRejected base
  openai_provider.py  OpenAI Responses API adapter (urllib, SSE → chunks + Usage, error mapping)
  anthropic_provider.py  Anthropic Messages API adapter
  google_provider.py  Gemini Interactions API adapter
  xai_provider.py  xAI Responses API adapter
  workloads.py     versioned benchmark workload catalogue (Workload, get_workload, list_workloads); deterministic synthetic prompts; imports nothing from llm_metrics
  benchmark.py     run_attempt(provider, workload, ...) (profile/price checks, measure, save) + print_summary, shared by CLI, real_smoke and real_benchmark
  real_benchmark.py  explicit one-paid-request pilot command for one chosen benchmark target
  real_smoke.py    explicit one-paid-request OpenAI connectivity check (real_benchmark.run with the smoke workload)
  latency.py       METRICS catalogue (label, unit); measure_request: outcome + token facts + metrics in one pass
  pricing.py       all prices (USD per 1M tokens) + PRICE_PROVENANCE + request_cost
  storage.py       SQLite init + transactional versioned upgrade; save_request; time-window reads; request reads; count_outcomes; spend_by_model
  seed_history.py  deterministic simulated TTFT history + seed command
  web.py           Flask HTTP boundary: create_app(), routes /, /requests, /spend, /api/v1/metrics, render_page (Jinja), json_response, status codes, CSP header, serving on 127.0.0.1
  analytics.py     product analytics as natural values: metric windows (successful observations + nearest-rank summary + success rate over all attempts), recent attempts, real-only spend totals
  query.py         product query definitions shared by HTML and JSON: metrics/units, windows, data populations, aggregate population, parameter validation, load_aggregate_metric
  api.py           JSON API v1 serializer (no Flask): analytics results -> JSON-ready facts, ISO UTC times, error bodies
  dashboard.py     page-specific query semantics + view preparation: requests/spend choices; formatting, "—"/"unknown", links, chart geometry (*_view / load_*_view); never reads storage
  templates/       Jinja templates: base.html, aggregate.html, requests.html, spend.html, invalid_query.html, partials (_aggregate_nav, _chart, _macros)
  static/          dashboard.css (served at /static/dashboard.css)
  percentiles.py   nearest-rank percentile (no HTML)
  object_results.py  immutable llm-metrics.attempt.v1 records: schema, canonical encoding, create-only GCS writes, read/validate
  scheduled_collector.py / collector_audit.py  bounded 15-minute collector with slot claims; read-only claims-vs-records audit
  record_analytics.py  offline read-only analytics over a local mirror of prod records -> canonical llm-metrics.analytics.v1 summary
  cost_ledger.py   private cost ledger -> sanitized /costs summary (actual charges only)
  publish_runner.py  local editorial and metrics release lanes (cadence, emergency switch, history)
  static_site.py   offline static site generator (Step 026: question registry, dated editions frozen into site_content/archive/): reviewed site_content/ + validated analytics summary -> HTML pages (site_templates/, site_static/)
  config.py        environment, DB path, dashboard port
  __main__.py      CLI
tests/             automated tests
prompts/           prompt history and guidance
design-questions/  interview-style design questions per step
data/              runtime DB; git-ignored
```

Flow: `environment → provider → measure_request (one stream → attempt with outcome + metrics) → price_for (+ request_cost on success) → print → save_request (attempt + observations, one transaction)`; dashboard: `GET /?window=&metric= → web route (Flask query args) → dashboard.parse_query → dashboard.load_aggregate_view → window_bounds(now) → analytics.load_metric_window (storage.load_observations / count_outcomes → Observation, MetricSummary, success rate) → dashboard.aggregate_view → view data (formatted values, chart coordinates) → web.render_page("aggregate.html") → Jinja (autoescaped HTML/SVG) → response (status, CSP)`.

SQLite (schema version 7, `PRAGMA user_version`; older databases upgrade in place, transactionally, keeping all rows):
- `requests` (one row per attempt): `id` (UUID hex, our identity), `recorded_at`, `environment`, `provider`, `model`, `outcome`, `input_tokens`, `requested_max_output_tokens`, `output_tokens`, `input_price_per_1m`, `output_price_per_1m`, `input_cost`, `output_cost`, `total_cost` (USD, unrounded), `failed_after_ms`, `provider_request_id` (OpenAI `x-request-id`; NULL when unknown), `workload_id`, `origin_cloud`, `origin_region` (required for new attempts; NULL for rows before Step 013), `cache_policy` (`disabled` / `enabled` / `provider_default` / `unknown`, CHECKed; `unknown` for rows before schema version 6), `cached_input_tokens` (provider-reported; NULL = not reported), `request_profile_id` (required for new attempts; NULL before schema version 7), `cached_input_price_per_1m` (cached rate of the cost basis; NULL when none). A CHECK enforces: success → tokens/costs known, `failed_after_ms` NULL; failure → tokens/costs NULL, `failed_after_ms` set.
- `observations`: `id`, `recorded_at` (UTC), `environment`, `provider`, `model`, `metric`, `value` (unit fixed by `metric`), `request_id` (NULL for pre-Step-010 and seeded rows).
A unique index on observations (`recorded_at`, `environment`, `provider`, `model`, `metric`) lets seeding skip existing rows.

`LLM_METRICS_DB_PATH` can override the default DB path; tests use temporary databases. SQL values are parameterized.

## Known limitations

- Real providers: four adapters exist, but only OpenAI has been exercised live (one successful smoke sample). The Anthropic, Google and xAI adapters are verified only against documentation and mocked fixtures; their first live requests are Step 016a. No benchmark workload has been sent to a real provider; no scheduling or repeated runs.
- Comparability (D062): the four targets share workload content, version, cap, origin and known request settings, not capability, tokenizer, reasoning or caching implementation, or infrastructure. Reasoning controls differ (Gemini Flash-Lite cannot turn thinking fully off); only OpenAI's request disables caching, so other providers may report cached input on repeated runs (recorded and priced at the cached rate, never inferred).
- Provider-protocol assumptions not yet confirmed live: Gemini Interactions `total_output_tokens` excludes thought tokens (output is stored as output + thought, per Google's billing description); Gemini "incomplete" has no reason field, so it counts as a cap stop only when reported output reached the cap; Anthropic and Gemini spend/quota-cap 429s are indistinguishable from rate limits and are recorded as `rate_limited`; Gemini and xAI request ids come from the stream body, so failures before the first event have none. The Google adapter uses the `v1beta` Interactions endpoint shown in Google's examples.
- Provider adapters remain our own code (about 1,300 lines over four providers): LiteLLM failed the measurement contract (D065), so provider API changes must be tracked by hand against official docs.
- Long-context price tiers and Anthropic cache-write rates are not modelled (all catalogue workloads stay within the standard tiers; no `cache_control` is sent).
- Workloads (D061): candidate hypotheses, not validated by user research. Input sizes are estimated at 4 characters per token, not measured with any provider's tokenizer, and will differ per provider. Generated material is repetitive by design (templated records), which may let providers' caches or models behave differently than on natural text. Answers are not checked; `agent-tool-v1` asks for a tool choice in plain text (no native tool calling). The provider request shape (e.g. OpenAI `reasoning.effort`) is fixed per provider and is not part of the workload id, except for the legacy smoke id. Existing aggregate views and `/api/v1/metrics` do not filter by workload, so simulated runs of different workloads share one population.
- The four early `provider_error` rows remain as validation history; their cause was not captured (presumed account credit, unconfirmed). They lower the observed real success rate (1 of 5).
- `provider_request_id` is NULL for attempts before Step 012a (not backfilled), simulated runs, connection failures, and failures detected only by measurement (e.g. the stream ended without a final event). It is stored but not shown on the dashboard.
- No whole-project budget guardrail yet (the `$10/day` operating budget is to be enforced when hosting/scheduling arrives); real spend is limited by running `real_smoke` or `real_benchmark` by hand, one request per command.
- Spend covers successful calls' known costs; providers may bill some failed calls, which stay unknown. Provider-reported cached input is priced at the cached rate (Step 016); cache-write rates are not modelled. Reasoning/thinking tokens are counted in output tokens for every provider.
- `./run.sh` uses the simulated provider only; one request per run, workload `interactive-chat-v1` (the dummy ignores the prompt's content apart from counting it, and always answers with 7 tokens).
- Token counts come from a simulated tokenizer (1 token per 4 characters) and prices are simulated; neither matches a real provider.
- `output_tokens_per_s` is observed effective throughput: whole-response token count over client-observed chunk timing. It includes first-chunk and reasoning tokens (reads high for very short responses) and is not internal decoding speed. Not backfilled for older attempts (the one real success has no tokens/s value).
- Cache: `disabled` for OpenAI rests on the prompt caching guide's documented explicit mode (GPT-5.6 and later); the gpt-6-luna page does not name the field, and it has not been exercised live. If rejected, the smoke run fails with HTTP 400 and records nothing. The smoke prompt (~17 tokens) is far below the 1,024-token caching minimum anyway, so caching could not affect it yet. Cache-write tokens are not stored. Only the metric-observation query has a cache-policy filter; success-rate and spend queries do not yet, and there are no cache comparison views.
- Origin is whatever the runner is configured to say; it is not verified. Rows before Step 013 have no workload or origin, and there are no origin/workload filters or comparison views yet.
- Observations recorded before Step 010 and seeded history have no request details and are not counted as attempts.
- No retries and no overall attempt deadline (OpenAI's 60 s timeout is per socket operation, so a trickling stream can take longer).
- Partial measurements of failed attempts (e.g. TTFT before a mid-stream failure) are discarded.
- Simulated history exists for TTFT only; total latency and throughput have only live measurements.
- Chunk throughput counts stream chunks, not provider tokens; the dummy's chunks are fixed (5 per response), and its token throughput uses the simulated tokenizer.
- Percentiles are reported the same way for every metric; for throughput (higher is better) the low tail (e.g. p5) would be more informative and is not shown.
- Simulated history uses a fixed past week; it moves out of the 24h/7d windows over time (after 2026-11-28 23:00 UTC it is outside all windows).
- Seeded and live dummy rows are both `test`/`dummy`; they are told apart only by timestamp (seeded rows are on the hour, before 2026-10-30).
- Dashboard has three fixed windows only; no custom ranges, provider filters, zoom, tooltips, or auto-refresh (reload the page).
- Within a window, seeded and live rows are still mixed (no source filter).
- Recent-attempt and spend-group rows still cross the analytics boundary as `storage` dicts (natural values, but untyped); view dictionaries are untyped too, so a mistyped key renders as an empty cell rather than failing.
- The dashboard and API use Werkzeug's single-threaded development server, fine for local use only; production serving is out of scope until deployment.
- The JSON API has one endpoint, fixed to the simulated dummy population (no provider/model selection), no authentication, no CORS (same-origin only), and no rate limiting. Its sample count can exceed its attempt count because seeded history has observations without attempt records (as on the aggregate page). Percentiles are full-precision floats; there is no published schema file (the contract is documented in README and D060).
- A fresh checkout needs network access to PyPI on its first `./run.sh` (and whenever `requirements.txt` changes); there is no offline wheel cache. Tests must run under the project venv.
- Non-GET requests now return 405 (previously 501); HEAD is answered automatically for GET routes.
- With fewer than 100 observations, nearest-rank p99 equals the maximum.
- Printing the page drops the label's background colour (browser print default).
- Migrations are hand-written upgrade steps in `storage._upgrade`; each schema change needs a new version and an upgrade test.
- A storage failure currently surfaces as a traceback after measurement output.
- `.venv` has no pip until a dependency is justified.
- `record_analytics` (Step 024):
  - It has run on synthetic fixtures only. The real Step 023 mirror has not been analysed.
  - Mirroring the bucket is a manual operator `gcloud storage cp`.
  - Slot completeness is tied to the Step 023 collector's fixed scope and a single 24-hour policy.
  - There are no confidence intervals: with fewer than 20 successes, p95 equals the maximum.
  - Only day directories that overlap the window are validated.
  - The SQL dashboard and the summary are not reconciled.
- `static_site` (Step 025):
  - Built and previewed locally only. No real dataset has been rendered.
  - Canonical URLs have no trailing slash, but directory-based servers redirect `/slug` to `/slug/`, so the host must support clean URLs.
  - There is no `robots.txt`, sitemap, HTTP security headers, dated versions or redirects yet (Steps 026/027).
  - No author or publisher is asserted, and `date_published` is unset until real publication.
  - The metric page is indexable even in its no-data state.
  - The editorial report is advisory; one sentence-length warning is open.

## Next step

**Recommended (Step 027c):** review the charts locally with `./run.sh site-preview`; then decide on `deploy staging`. Tomorrow: approve `stop` and the audit for the original pilot before any Approval C.

_Previous:_
**Recommended (after ChatGPT review of Step 027b):** after 18:00Z approve the documented `stop`, run the full-window audit and rebuild staging from the complete 96-slot dataset.

_Previous:_
**Recommended (after ChatGPT review of Step 027a):** review and approve the ready drafts in a local preview, then rebuild staging.

_Previous:_
**Recommended (after ChatGPT review of the staging deploy):** a browser visual and accessibility review of https://llmxchange.akuchlous.workers.dev, then Approval B (domain, publication, Search Console) when ready.

_Previous:_ **Recommended (after ChatGPT review of Step 027):** Approval A, a Cloudflare `*.workers.dev` staging deploy; done 2026-11-07.

_Previous:_ **Recommended (after ChatGPT review of Step 026):** review and approve the draft duplicate-calls article, then follow the minimum publication steps in `prompts/026-output.md`: publish with `--publish-at`, commit the archive, then an approved hosting step (027).

_Previous:_ **Recommended (after ChatGPT review of Step 025):** decide the publication order under the new "publish educational content early" priority. The shortest safe path is in `prompts/025-output.md`: review the article, then an approved, minimal hosting step that serves the no-data build, before or alongside Step 026.

_Previous recommendation:_ **Recommended (after ChatGPT review of Step 024):**
1. Close Step 023 once the window ends at 2026-11-07T18:00Z: run the post-window audit and the stop.
2. Then, with explicit approval, make a read-only local mirror of `attempts/v1` and run `record_analytics` over the full 96-slot window with `--collector-policy-start 2026-11-06T18:00:00Z`. This produces the first real `llm-metrics.analytics.v1` summary.

Step 025 must consume only that summary.

_Earlier proposal, kept for history:_ **Step 018i (proposed):** Provision a new Cloud SQL `db-f1-micro` instance; rebuild and redeploy the Cloud Run Job image with the 018h guard; run one new OpenAI measurement; verify the guard fires when DATABASE_URL is absent; export and back up results; delete Cloud SQL. No new providers, no scheduling.

Do not yet add more models, a scheduler, repeated benchmark runs, authentication, price scraping/history, or workload matrices without a numbered prompt. Do not provision GCP resources, build/push images, or make paid API calls without explicit bounded user authorization in this session. Do not execute the existing Cloud Run Job (image `app:sha-9cf8ac9`, pre-guard).
