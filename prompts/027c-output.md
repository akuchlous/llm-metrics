# Step 027c output — Real pilot charts and plan-only 24-hour restart

## Status: COMPLETE locally; NOT deployed. Awaiting your local visual review ("deploy staging") and ChatGPT review.

## Part A — Charts from real measurements
- **Data:** the same private read-only mirror as Step 027b (taken 2026-11-07T15:26:57Z), no new GCS reads or OpenAI calls. Status: **partial pilot**, cutoff 2026-11-07 15:30:00 UTC; 86 of 96 slots due: 85 successes, 1 provider error (slot 2026-11-06T21:30Z), 0 missing, 0 claims without record; 10 not yet due.
- **New `llm_metrics.pilot_series`** (`llm-metrics.pilot-series.v1`): one row per policy slot with state (`success`, `failure` + category, `missing`, `claim_without_record`, `not_due`) and, for successes, that request's TTFT, total latency and output tokens/s rounded to 0.1. It reuses `record_analytics.load_records` and `slot_evidence`, reads claims by `claim_name`, and refuses disagreement with the audit. No ids, object names, prompts or responses.
  - Pilot series SHA-256 `d31aa1bd2c8e437a813c72a412ee2275b0338938ccebfb44c409ccb9dae5b5a4`; record manifest `48c453165ad31480bfc74a4f5f1837a75ab64fe9284c4214cab3357e7345ff00` (same as the analytics summary `763fd4b0…`).
- **`static_site --series FILE`** (with `--analytics`): `load_series` refuses a different manifest hash, population or counts, out-of-order slots, future slots that disagree with the cutoff, non-allowlisted fields or non-canonical bytes. The file is published at `/data/series/<sha256>.json`.
- **Metric page `/metrics/openai/ttft`**, new section "Every request over time" (static SVG, no JavaScript):
  - TTFT, total response time and output tokens/s per request over UTC time. Each dot is one request ("not an average"). Lines join only consecutive successes; failed, missing and claim-without-record slots are ✕ on the axis; future slots are a shaded "not yet due" band. Dashed median line, labelled nearest-rank with n.
  - Outliers: when the maximum exceeds 2 x p95, the axis stops at a round number above 2 x p95 and slower requests are drawn as ▲ at the top edge with their value. Pilot: TTFT axis 0–6,000 ms with one request labelled 12,343 ms; total response time 0–15,000 ms with one request labelled 15,236 ms (the same slow slot); tokens/s 0–150 (no capping).
  - Outcome strip of all 96 slots with a legend: 85 successful, 1 failed, 0 missing, 0 claimed without record, 10 not yet due.
  - Accessible: `role="img"`, `<title>`, `<desc>`, captions, theme colours from CSS (light/dark), and a 96-row table in `<details>`.
- `/openai-ttft` (evidence view) links to the charts. The homepage stays the question list.
- **Measured vs illustrative:** every chart on the site uses real pilot data only. The synthetic fixture is used in tests only.
- **Preview:** `./run.sh site-preview` picks up `.site-preview/analytics.json` and `.site-preview/series.json` (both gitignored, private) automatically; `--series` was added and the script now fails closed instead of serving a stale build.

## Part B — Plan-only 24-hour restart
- **`./run.sh pilot-plan --start YYYY-MM-DDTHH:MM:SSZ [--analytics SUMMARY] [--json]`** (`llm_metrics.pilot_plan`, run in Docker with no network): prints run id (`openai.gpt-6-luna.v1/<start>`), window and 96 slot times, resources reused, the exact launch changes, prerequisites, cost estimate, and `activate`/`audit`/`stop`/rollback commands. It runs no gcloud command, reads no secret and calls no provider; `--execute` is always refused.
- **Refusals:** not a UTC quarter hour; less than 30 minutes or more than 14 days ahead; overlap with a registered run (including the 7-minute late-record limit); a repeated start; a previous run not closed. The window is always the collector's own 96-slot `Policy`.
- **Registry** `scripts/gcp/pilot_runs.json`: the original run, `closed: false` until its `stop` and audit.
- **Run identity and comparison:** claims are per slot time, so non-overlapping windows share no claim; `record_analytics`/`pilot_series` select a run by its policy start and end, so pilots never mix. Records stay immutable.
- **Cost (example from the partial pilot summary):** expected about $0.0315 for 96 requests, upper bound about $0.047 (mean input tokens x 1.5 and the 300-token output cap at stored prices). Estimates from tokens, not billing. GCP usage expected within free tiers (not verified).

### Approval C (future, not requested yet)
Tomorrow (2026-11-08, Asia/Kolkata), in order:
1. Approve and run `bash scripts/gcp/023_collector.sh stop` (the original pilot's scheduler and key are still attached after 18:00Z), then the post-window audit; set the run `closed: true`.
2. Choose a UTC start and run `./run.sh pilot-plan --start <UTC> --analytics <reviewed final summary>`.
3. Approve explicitly: run id, start/expiry, provider OpenAI, model `gpt-6-luna`, profile `openai.gpt-6-luna.v1`, 15-minute cadence, at most 96 paid requests, the cost cap, key `OPENAI_API_KEY`, region us-central1, records under the results bucket's `attempts/v1/requests/prod/`, the stop and audit commands.
4. Only then: `bash scripts/gcp/023_collector.sh activate <UTC>` and add the run to the registry.
No start time is chosen here.

## Tests
- New `tests/test_pilot_series.py` (19 tests): 96 rows and states, exclusive cutoff, rounding and null throughput, no ids, manifest equality, out-of-policy end refused; `load_series` refusals (manifest, extra field, future-as-success, counts, order, non-canonical); chart gaps, marks, future band, throughput n, outlier capping, axis rounding, accessible static SVG, 96-row table, published bytes; plan bounds, refusals, overlap/duplicate/open-run, partitioning, cost, `--execute` refused, no cloud/provider imports, registry ids.
- Full Docker `./run.sh test`: 689 tests, OK (7 skipped). Lint clean.
- Local preview built (9 pages, real dataset) and served; the metric page had 3 time-series charts, the outcome strip, medians 1,637 ms / 4,279 ms / 116.7 tokens/s, counts 85/1/10, and the labelled 12,343 ms and 15,236 ms outliers.

## Limitations
- Partial window; the charts will change after the full audit.
- No screenshot was possible in this session (no browser or SVG rasteriser); the visual check is yours, in `site-preview`.
- The preview and `./run.sh test` both use port 8000.

## Cost and approvals
No GCS reads (reused the 027b mirror), no OpenAI calls, no Cloudflare deploy, no GCP changes. Step 023 untouched.

## Recommended next step (one)
Review the charts locally with `./run.sh site-preview`; if they look right, say "deploy staging".

## MARKETING CHECKPOINT
- **Shareable privately after review:** per-request charts of the partial pilot, labelled provisional.
- **Not publishable yet:** any final or 24-hour figure, general claims about OpenAI latency, rankings, cost as billed spend, production metrics (Step 028 and Approval B).

## Design Q&A (concise)
- **Lead engineer:** gaps, failures and future slots stay visible; outliers capped but labelled.
- **Principal engineer:** the series carries the same manifest hash as the summary and is refused otherwise.
- **Senior manager:** close the pilot, plan, then a separate Approval C; cents per run.
- **Director:** repeat runs are cheap evidence; keep each deliberate.

Full files: `design-questions/027c/`.

## Follow-ups (2026-11-07)
- Every page heading is a question (D090).
- No data downloads: the dataset and series links and `data/` files were removed; fingerprints stay as text (D091).
- **Deployed to staging at the owner's request** ("deploy to cloudflare"): Worker `llmxchange` version ff23ce00-3739-4c0a-9efb-ba50390b105e (previous 4843a1e5) on Workers Static Assets, not Cloudflare Pages. Live: all pages 200 and byte-identical to the build; charts and "Partial pilot, as of 2026-11-07 15:30:00 UTC" on `/metrics/openai/ttft`; the old `/data/analytics/...json` now 404; drafts 404; `noindex, nofollow`. 691 tests OK (7 skipped).

**STOP: awaiting ChatGPT review. Step 028 and Approvals B/C not started.**
