# Step 028 output — Production thresholds, metric snapshots, complete pilot published

## Status: PARTIAL. Phase 0 core done and the complete pilot published on llmxchange.com at the owner's request. Weekly cloud publisher, weekly cost editions and the answer-review report are NOT built. Awaiting ChatGPT review.

## Done
- **Production thresholds** (`static_site.production_gate`, applied by `build` to every real dataset outside staging, so also by `publish_runner`): complete 24-hour window (no `partial_day`), collector evidence for every policy slot, at most 5% of slots without a record, at least 50 successes. `--allow-preliminary` can no longer publish a partial window. Passing data carries a scope label: "Complete 24-hour pilot, <start> to <end> UTC: one model, one workload, one region. Not a provider-wide benchmark or ranking."
- **Dated immutable metric snapshots:** with `--publish-at` and a gated dataset not yet snapshotted, the metric page is frozen at `/reports/<date>/openai-ttft-measurements` (`/rN` for repeats on one day) into the committed archive. The manifest's new `metric_snapshots` list holds route, published time, dataset SHA-256, record manifest SHA-256, window, methodology version, site URL and HTML SHA-256. Snapshots are served verbatim, refused if modified, canonical to `/metrics/openai/ttft`, outside the sitemap, and listed on the metric page under "Which measurement snapshots have been published?". The same dataset never creates a second snapshot. Staging ignores the archive.
- **Published (production, Worker version d6f9c6e1-67b6-4c31-b536-16674aa43f04):** `--publish-at 2026-11-08T06:38:19Z` with the complete pilot summary (sha256 `a01202f715bf8b97d853813476724002fa77248a8101bc50bf1901b3e7a3ae23`) and series (`bbcdfaf7487aa72242c7f06b3eedd0b40a66e1bbcabee44feb4567b63e4decb9`). `/metrics/openai/ttft` is now indexable and in the sitemap (11 URLs), with the four charts and the snapshot `/reports/2026-11-08/openai-ttft-measurements`.

## The published numbers (2026-11-06 18:00 to 2026-11-07 18:00 UTC)
- Audit (read-only, 2026-11-08T06:28Z): 96/96 slots claimed and recorded; 95 successes, 1 `provider_error` (2026-11-06T21:30Z); 0 missing; 0 claims without record; 0 records without claim.
- TTFT p50 1,631 ms, p95 2,594 ms (min 929, max 12,343). Total response time p50 4,241 ms, p95 5,917 ms. Output 117.8 tokens/s p50. Nearest-rank, successes only, n = 95 (small-sample caveat shown).
- Tokens 170,525 input, 28,275 output. **Estimated** model cost $0.03119 for 95 priced successes (token counts x stored prices, not billing); the failed request's cost is unknown.

## Not done (remaining Step 028 scope)
- Weekly cloud trigger (Cloud Scheduler to a short-lived Cloud Run job, Sunday 02:00 UTC): needs Approval A (staging) and B (production) and an architecture/cost review.
- Weekly dated cost editions (`/reports/<date>/project-costs`), billing exports/connectors, the weekly-job cost line.
- Machine-readable "answer review needed" report. Today every approved answer is methodology-only (`_EMPIRICAL_RE` refuses measured values in reviewed prose), so new numbers cannot contradict an answer; the report is still needed before answers cite data.

## Tests
- New: `ProductionGateTest` (partial window refused even with `--allow-preliminary`; success and unrecorded thresholds; `build` applies the gate) and `MetricSnapshotTest` (created once, served verbatim, canonical, not in sitemap, listed on the metric page; modified snapshot refused; staging never snapshots). Runner tests bypass the gate explicitly because they test lane logic with the 2-hour fixture.
- Full Docker `./run.sh test`: 698 tests, OK (7 skipped). Lint clean.
- Live: all pages 200 and byte-identical to the build; drafts and unknown paths 404; no `data/` files; scope label, medians and outcome counts present.

## Cost and approvals
Read-only GCS mirror of existing objects (negligible). One production deploy of the existing Worker at the owner's request ("deploy all charts ... and step 028"). No OpenAI calls, no GCP changes, no scheduler. The Step 023 `stop` (scheduler pause, key detach) is still pending approval.

## Limitations
- One model, one workload, one region, one day; p95 from 95 successes.
- `/openai-ttft` (metric question) is still a draft and absent from production.

## Recommended next step (one)
Approve `bash scripts/gcp/023_collector.sh stop` to close the pilot; then decide on Approval A for the weekly publisher.

## MARKETING CHECKPOINT
- **Publishable:** "In a complete 24-hour pilot (Nov 6–7, 2026, 96 scheduled requests from us-central1), OpenAI gpt-6-luna's median time to first token was 1.63 s (p95 2.59 s); 95 of 96 requests succeeded", with the scope.
- **Not publishable:** rankings or comparisons, "OpenAI is fast/slow" in general, uptime/SLA claims, the estimated model cost as billed spend, lifetime project cost totals.

## Design Q&A (concise)
- **Lead engineer:** snapshots are create-only, hash-checked and idempotent per dataset.
- **Principal engineer:** the gate sits in `build`, so the runner cannot publish partial data.
- **Senior manager:** the complete pilot is public and scoped; the weekly publisher remains.
- **Director:** one dated, scoped observation is publishable; comparisons are not.

Full files: `design-questions/028/`.

**STOP: awaiting ChatGPT review. Weekly publisher (Approvals A/B) not started.**
