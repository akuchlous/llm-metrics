# Step 027b output — First real OpenAI metrics on Cloudflare staging

## Status: COMPLETE (provisional, partial window); staging updated; awaiting ChatGPT review.

**Staging:** https://llmxchange.akuchlous.workers.dev/openai-ttft and https://llmxchange.akuchlous.workers.dev/metrics/openai/ttft (`noindex, nofollow`). Worker `llmxchange` version 4843a1e5-8c9e-4c62-b45e-aa25c07e2530 (previous 7e8681e8-1ae2-453b-af1e-44acbe5c6f9b).

**Label shown:** "Partial pilot, as of 2026-11-07 15:30:00 UTC; not a 24-hour result or provider-wide benchmark." The pilot window (2026-11-06T18:00Z to 2026-11-07T18:00Z) was still running; this is **not** a verified complete pilot.

## Read-only inventory (mirror taken 2026-11-07T15:26:57Z)
- Mirror: `gcloud storage cp -r` of `attempts/v1/claims` and `attempts/v1/requests` into a private scratch directory (not in Git). Files: 86 prod claims, 1 dryrun claim, 87 prod records (25 dated 2026-11-06, 62 dated 2026-11-07), 2 test records (never read by analytics).
- `collector_audit --start 2026-11-06T18:00:00Z --expires 2026-11-07T18:00:00Z --mode prod`: expected so far 86, claimed 86, recorded success 85, recorded failure 1 (`provider_error`, slot 2026-11-06T21:30Z), missing 0, claim without record 0, records without claim 0, claims outside policy 0, invalid records 0. Not-yet-due slots (10, 15:30Z to 17:45Z) are not counted as missing.
- Population (unchanged code/config): openai, `gpt-6-luna`, `openai.gpt-6-luna.v1`, `interactive-chat-v1`, gcp/us-central1, prod. One prod record outside the window (earlier pilot) excluded by filter.

## Analytics (unchanged Step 024 `record_analytics`)
`record_analytics --input <mirror> --provider openai --model gpt-6-luna --profile openai.gpt-6-luna.v1 --workload interactive-chat-v1 --origin gcp/us-central1 --start 2026-11-06T18:00:00Z --end 2026-11-07T15:30:00Z --collector-policy-start 2026-11-06T18:00:00Z`
- Private summary SHA-256 `763fd4b0074f454d6f84a277e9c3eb33cfed19c341738acc762f68f956f5760c`; record manifest SHA-256 `48c453165ad31480bfc74a4f5f1837a75ab64fe9284c4214cab3357e7345ff00`; 86 records.
- Published allowlisted summary SHA-256 `42d8217bf223304efb94e9078efde1ef8ae40fa6003c1804b89ef54d93c3a49c` (per-record object names and attempt ids removed).

| Metric (successful requests, nearest-rank) | N | p50 | p95 | Min | Max |
|---|---|---|---|---|---|
| TTFT (ms) | 85 | 1,637 | 2,551 | 929 | 12,343 |
| Total response time (ms) | 85 | 4,279 | 5,917 | 3,391 | 15,236 |
| Output tokens/s | 85 | 116.7 | 133.9 | 77.0 | 136.2 |

- Reliability: 86 attempts, 85 successes, 1 provider error; observed success rate 98.8% (not uptime).
- Tokens (successes): 152,575 input, 0 cached input, 25,298 output. **Estimated model cost** from reported tokens and stored list prices: $0.027907 for 85 successes; the failed attempt's cost is unknown (not $0). This is not billed cost.
- Caveats shown: partial day, small sample (fewer than 100 successes), observed success rate, failed cost unknown.

## Code changes
- `static_site --provisional-metrics` (requires `--staging` and a `real` dataset): pilot gates (`PROVISIONAL_MIN_SUCCESSES = 30`, at most 5% of due slots unrecorded, slot evidence required), the provisional label with the exact UTC cutoff and due-slot denominator, and an allowlisted public JSON with `public_projection` metadata. Without the flag nothing changes; `publish_runner` never uses it and keeps its complete-day and `--allow-preliminary` gates (D087).
- Generated **evidence view** for draft metric questions with a provisional dataset: `/openai-ttft` shows the question, "Measured values only… not been editorially approved", and generated tables. Its draft answer prose is not published and it stays `draft`.
- Templates: provisional notice on findings and measurements; provenance shows both hashes.

## Tests
- New `tests/test_site_provisional.py` (8 tests): staging/real requirement, minimum successes, slot evidence, unrecorded-slot share, partial label and allowlisted JSON, unchanged production path, evidence page without draft prose and no dated editions, no evidence page without provisional data.
- Focused site suites: 128 OK. Full Docker `./run.sh test`: 664 tests, OK (6 skipped). Lint clean.
- Pre-deploy: forbidden-pattern grep clean (no object names, attempt ids, provider ids, project/bucket names, emails, keys); drafts absent; every page `noindex, nofollow`; archive unchanged; `wrangler deploy --dry-run` passed.
- Live: `/`, `/openai-ttft`, `/metrics/openai/ttft`, `/useful-llm-api-metrics`, `/llm-performance`, `/questions`, `/how-to-measure-openai-ttft`, `/costs` 200; `/openai-ttft/` 307; drafts and unknown paths 404; public JSON 200 `application/json`, byte-identical, no `attempt_id`; pages byte-identical to the build and contain the values above and the provisional label; `X-Robots-Tag: noindex, nofollow`; `cache-control: public, max-age=0, must-revalidate`; sitemap has no URLs.

## Approval scope, cost, safety
- Used: read-only GCS list/get on existing objects (about 180 small objects; negligible cost), local Docker, one update of the existing free staging Worker.
- Not done: no OpenAI calls, no Step 023/collector/scheduler/IAM/GCS changes, no new Worker, no domain, DNS, production, Flask, database or scheduler. No raw records, mirror or credentials in Git.
- **Operational risk to report:** after 18:00Z the collector no-ops, but the scheduler stays enabled and the key stays attached until `bash scripts/gcp/023_collector.sh stop` is run. That needs your separate approval; it was not run.

## Limitations
- Partial window (86 of 96 slots); values will change. One origin, one workload, one model; small sample.
- The live page's `/how-to-measure-openai-ttft` findings section also shows these provisional values.
- No screenshots or Lighthouse (headless browser not permitted earlier).

## Recommended next step (one)
After 18:00Z: approve the documented `stop`, then run the full-window audit and rebuild staging from the complete 96-slot dataset ("verified complete pilot" label if it passes).

## MARKETING CHECKPOINT
- **Shareable privately (staging, labelled provisional):** the partial pilot numbers with their label.
- **Not publishable yet:** any figure as a final or 24-hour result, any claim about OpenAI in general or rankings, production publication (needs Step 028 snapshots and Approval B), the estimated cost as actual spend.

## Design Q&A (concise)
- **Lead engineer:** partial data reaches only `--staging --provisional-metrics`; the production lane never uses it.
- **Principal engineer:** the public JSON is an allowlisted projection that records the private hash it came from.
- **Senior manager:** real numbers are visible with a conspicuous provisional label; no general claims.
- **Director:** right for staging; production gates unchanged.

Full files: `design-questions/027b/`.

**STOP: awaiting ChatGPT review. Step 028 and Approval B not started.**
