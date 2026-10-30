# Step 008 — Implementation report

Prompt: `008-total-response-latency.md`.

## What was implemented

- `measure_latency(provider, prompt)` streams one response and returns **TTFT** and **total response latency** (`total_latency`), both timed from the same request start.
- The CLI prints both and saves both rows in one transaction with the same `recorded_at`.
- The dashboard gains a **TTFT / Total latency** selector (`?metric=`, default `ttft`) alongside the 24h/7d/30d windows. Count, latest value, p50/p95/p99 and chart all come from the selected metric and window's rows.

## Files

- `llm_metrics/latency.py` (renamed from `ttft.py`) — `measure_latency()`, which replaces `measure_ttft()`.
- `llm_metrics/providers.py` — `DummyProvider(inter_token_delay_s=0.02)` waits between tokens after the first.
- `llm_metrics/storage.py` — `save_observations(results)` (one transaction, shared timestamp) replaces `save_observation(result)`.
- `llm_metrics/__main__.py` — prints `TTFT`, `Total latency`, `Saved 2 observations`.
- `llm_metrics/dashboard.py` — `METRICS`, `parse_query()` (window + metric, shared `_parse_choice`), metric-aware nav, labels and 400 page; `build_page(db_path, window, metric, now)`.
- Tests: `test_latency.py` (renamed and rewritten), `test_providers.py`, `test_storage.py`, `test_dashboard.py`, `test_cli.py`, `test_run_script.py`.
- `README.md`, `PROJECT_STATUS.md`, `DECISIONS.md` (D032, D033), `design-questions/08/`.

## Tests / run

- 70 tests, OK (~13 s).
- Clean `./run.sh`: `TTFT: 100.3 ms`, `Total latency: 180.9 ms` (= 100 ms + 4 × 20 ms gaps), `Saved 2 observations`.
- Dashboard: `/` showed TTFT n = 164 (7d); `/?metric=total_latency` showed n = 1 (live only); `?metric=bogus` and a repeated `metric` both returned 400.
- `APP_ENV=prod ./run.sh` still exits 2.
- No runtime artifacts or secrets staged; the bind address and CSP are unchanged.

## Design decisions and tradeoffs

- **No schema change.** Each metric is its own row (`metric = 'ttft'` / `'total_latency'`). The unique index already includes `metric`, so two rows sharing `recorded_at` are valid. Queries filter on `metric`, so the populations can't mix.
- **One pass, one request.** The provider is called once; TTFT is captured at the first token and total latency after the loop. A test with a counting provider checks one call and full consumption.
- **All or nothing.** Both rows go in one transaction with one timestamp. A failed stream raises before saving, so no orphan TTFT row exists without its total. A test forces a NOT NULL violation in the second row and checks zero rows were saved.
- **Metric name `total_latency`.** It's explicit about what's measured (end-to-end response time), and the unit stays in `value_ms`. "e2e" or "duration" are ambiguous next to TTFT.
- **Same input rules as `window`:** unknown, empty or repeated values give a 400, the value is never echoed, and links keep the other selection.
- **Simulated history unchanged.** It covers TTFT only, so total latency shows live points only. Seeding total-latency history wasn't requested; it would be a separate decision.
- **API rename** (`measure_ttft` → `measure_latency`, `save_observation` → `save_observations`). All callers are internal, so there's no compatibility shim.

## Design Q&A

**Why measure both metrics in one pass instead of two calls?**
Two calls would measure two different requests: different queueing, cache state and network conditions. A request's total latency could then be lower than its "own" TTFT, which is nonsense. One pass guarantees `total >= ttft` per request, halves cost for real providers, and lets the two rows share a timestamp for pairing later. *Tradeoff:* TTFT now waits for the full stream before it's saved; a stream that hangs delays both.

**Why separate rows instead of a `total_ms` column?**
The existing model is one observation per metric. A column would be a schema change and would make every query and percentile per-column. Separate rows reuse the time-window filter, the percentile code and the dashboard unchanged, with `metric` as a filter. *Cost:* pairing TTFT with total latency for the same request relies on the shared `recorded_at` rather than a request ID.

**What does total latency tell you that TTFT doesn't?**
TTFT is responsiveness (when the user sees something). Total latency is completion time, which is dominated by output length times per-token speed. Two providers with equal TTFT can differ widely in total latency. Total latency isn't comparable across responses of different lengths; that needs throughput (tokens per second), which is the next step.

## Limitations / review questions

- Total latency depends on response length, and the dummy always emits 5 tokens. With real providers, compare total latency only for similar output sizes.
- There is no request ID; pairing of the two metrics relies on the identical `recorded_at`.
- Total latency has no simulated history, so its windows show live runs only.
- A stream that errors after the first token saves nothing; partial-stream failures aren't recorded (error metrics are out of scope).
