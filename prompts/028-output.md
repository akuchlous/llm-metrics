# Step 028 output — Weekly publication, cost editions, answer review (Phase 0 complete)

## Status: Phase 0 DONE (offline). Approval A (staging cloud job) and Approval B (production schedule) NOT started: they need fresh, scoped owner approval. No schedule is enabled. Awaiting ChatGPT review.

## Part 1 (2026-11-08, earlier)
- **Production thresholds** (`static_site.production_gate`): complete 24-hour window, evidence for every slot, at most 5% unrecorded slots, at least 50 successes. Applied by `build` to every real dataset outside staging.
- **Dated immutable metric snapshots** `/reports/<date>/openai-ttft-measurements`, keyed by dataset SHA-256, served verbatim, refused if modified.
- **Complete pilot published** on llmxchange.com (Worker d6f9c6e1): TTFT p50 1,631 ms / p95 2,594 ms, 95/96 successes, snapshot `/reports/2026-11-08/openai-ttft-measurements`.
- Then, at the owner's request: collector stopped (scheduler paused, key detached, alert disabled; run closed) and `/openai-ttft` approved and published (Worker 530c17b2, edition `/reports/2026-11-08/openai-ttft`).

## Part 2 (this change): Phase 0
- **Weekly publisher** `python -m llm_metrics.weekly_publisher` (`llm_metrics/weekly_publisher.py`): one run per week, Sunday 02:00 UTC (`publishing.json`: `weekly_day`, `weekly_run_at_utc`). Publication only: no collection, no provider, GCP, Cloudflare or billing calls. Per run it decides separately:
  - **metrics**: `publish` (passes the production gate, window ended before the scheduled run, new dataset, no answer review needed), `no_change`, `no_new_data`, or `held` with the precise reason (gate message, window after the run, older snapshot, review needed). Held/unchanged runs rebuild from the accepted copy in the private state dir, which must match the latest published snapshot, so metric pages never roll back or vanish.
  - **costs**: `publish` a dated `/reports/<date>/project-costs` edition when the public cost content changed, `no_change`, `stale` (cut-off > 8 days old: disclosure on /costs, no edition) or `no_billing_input`. An invalid ledger refuses the whole run (nothing written).
  - **answer review**: private machine-readable report `<state-dir>/reviews/<date>.json`, one row per approved answer linked to a metric: `not_needed` (methodology answer), `current`, or `review_needed` (dataset-based answer reviewed against another dataset), which holds the metrics update. Nothing is ever approved or rewritten.
  - **Idempotent**: each week recorded in `state.json`; a retry returns `already_done`. Archive writes are keyed by content (dataset hash, cost content hash, edition id), so even a crash between freeze and record cannot duplicate. No catch-up of missed weeks. `--dry-run` writes nothing. `publishing_enabled: false` stops everything.
- **Cost ledger** (`cost_ledger.py`): optional source `category` (`llm_api`, `subscription`, `cloud`, `hosting`, `domain`, `weekly_publishing`, `other`); `weekly_publishing` sources summarized separately as **charged or "pending reconciliation"**, never a modeled figure; `content_sha256` ignores timestamps (re-verified unchanged ledger = no edition); `stale()`.
- **Cost editions** in `static_site`: `cost_editions` manifest list, served verbatim, hash-checked, canonical to /costs, outside the sitemap, listed on /costs under "Which cost updates have been published?".
- **Fix**: `build` now checks the output path before freezing (the 2026-11-08 build froze an edition, then refused the output). Archive stray-file check now includes cost editions.
- **Real-data dry run** (2026-11-08T10:30Z, complete pilot + current ledger): metrics `no_change` (already published), costs `publish` (first cost edition would be `/reports/2026-11-08/project-costs`), answer review `not_needed` for q0001, q0006, q0007. Not executed for real: the first cost edition goes out with the first approved weekly run or an owner-requested publish.

## Proposed cloud architecture (for Approval A; nothing created)
- **Cloud Scheduler** job `llm-metrics-weekly-publisher` (`0 2 * * 0`, UTC), **created paused**, calling the Cloud Run Jobs API with the existing `llm-metrics-scheduler@` SA (`roles/run.invoker` on this job only). Retries: 0 (the job is idempotent anyway).
- **Cloud Run Job** `llm-metrics-weekly-publisher`, same project image plus Node/Wrangler 4.152.0, 1 vCPU / 1 GiB, timeout 10 min, max retries 1, no always-on service. Steps: download inputs, archive and state from a private bucket prefix → `weekly_publisher` → if published or changed, `wrangler deploy` (staging under A, production under B) → upload new archive files create-only (`if-generation-match=0`) and state.
- **New SA** `llm-metrics-publisher@`: `storage.objectViewer` on `publication/inputs/`, `storage.objectCreator` + viewer on `publication/archive/` and `publication/state/` (IAM conditions on the existing private results bucket or a new private bucket), `secretmanager.secretAccessor` on a new `CLOUDFLARE_API_TOKEN` secret only (token scoped to Workers Scripts edit on one account). **No** access to `OPENAI_API_KEY`, collector records, billing accounts or BigQuery billing export.
- **Inputs** stay operator-reviewed: the analytics summary, series and private cost ledger are uploaded by the operator after review. Billing exports and provider billing connectors are proposed only; no access requested.
- **Archive of record** stays git: the operator commits archive files the job created (job log prints the routes and hashes).
- **Pause**: `gcloud scheduler jobs pause llm-metrics-weekly-publisher`, or `publishing_enabled: false` in the uploaded config. Rollback: redeploy the previous Worker version (`wrangler rollback`); archived editions are never deleted.

## Cost (estimates, not charges)
- Scheduler: 1 job (3 free per billing account) → USD 0 expected.
- Cloud Run Job: ~2–3 min/week at 1 vCPU/1 GiB ≈ 600 vCPU-s/month, inside the free tier → USD 0 expected.
- Storage/Secret Manager/egress: KB–MB scale, inside free tiers → USD 0 expected.
- Cloudflare Workers static assets: free plan.
- Expected under USD 0.10/month even outside free tiers. **Unverified**: shown on /costs as "Weekly publishing operations — pending reconciliation" until a billing statement shows the actual charge. Budget alerts are notifications, not spending caps.

## Charged vs estimated, source coverage
- Charged and owner-reported: ChatGPT USD 20, Claude USD 20, domain USD 12 (receipts not attached).
- Unknown: OpenAI API (estimated model cost USD 0.03 for the pilot is not a charge), Google Cloud. The lifetime total remains "not yet verified".

## Approvals
- Part 2 is offline only: no cloud, provider, billing or deploy action. No Step 023 change.
- **Approval A** would allow: create the publisher SA, secret, paused scheduler and job; run it against **staging** only; verify duplicate invocation, no-op week, failure rollback and sanitized logs.
- **Approval B** would allow: point the job at production and resume the schedule.

## Security review
- Private ledger references are refused in public output (`scan_public`), tested with the weekly run. Review reports and state live only in the private state dir.
- The publisher imports no network, cloud or provider client. The proposed job SA cannot read the OpenAI key or billing data.

## Tests
- New `tests/test_weekly_publisher.py` (22 tests): schedule math, first week publishes and retry is a no-op, unchanged week adds nothing and keeps numbers, new dataset adds one snapshot, gate failure held, window after the run held, stale ledger, invalid ledger refuses, missing accepted copy refused, dry run writes nothing, disabled publishing, private review report, review statuses, review-needed holds metrics, committed answers need no review, cost content hash, weekly publishing never modeled, unknown category, stale boundary, modified cost edition refused, output checked before freeze.
- Full Docker `./run.sh test`: **720 tests OK (7 skipped)**. pyink/isort/pylint: no findings in changed files.

## Limitations
- Dataset-based answers are still refused by the site (no answer cites a snapshot yet); the review path for them is tested at the report level.
- Inputs are produced by the operator; the weekly job does not run Step 024 analytics or mirror records.
- The cost of the weekly job is unknown until billed.

## MARKETING CHECKPOINT
- Publishable: the scoped pilot result (unchanged from part 1); "the site publishes a dated cost update each week there is new billing evidence".
- Not publishable: rankings, lifetime project cost totals, the job's cost as a number.

## Recommended next step (one)
Owner decides on **Approval A** (staging weekly job, paused scheduler, new least-privilege SA and Cloudflare token).

**STOP: awaiting ChatGPT review.**
