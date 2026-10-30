# Step 009 — Implementation report

Prompt: `009-throughput.md`.

## What was implemented

- **Output throughput** `output_chunks_per_s` = (non-empty chunks − 1) ÷ (time of the last non-empty chunk − time of the first), measured in the same single pass as TTFT and total latency. `measure_latency` was renamed `measure_request` and returns a list of results.
- A **chunk** is one non-empty item from `provider.stream()`. For the dummy provider that's one simulated token; it is not an API token.
- Throughput is **omitted** when undefined (fewer than 2 non-empty chunks, or zero elapsed time).
- The CLI prints three metrics with units and saves them in one transaction.
- The dashboard selector gains **Output throughput**; labels, percentiles, the latest value and the axis use the metric's unit (`chunks/s`, never `ms`).
- **Schema version 1:** `value_ms` is renamed to `value` (see below). Version-0 databases are upgraded in place on connect and keep their rows.

## Files

- `llm_metrics/latency.py` — `METRICS` catalogue (name → label, unit); `measure_request()`.
- `llm_metrics/storage.py` — `value` column, `SCHEMA_VERSION = 1`, `_upgrade()` (`PRAGMA user_version`, `ALTER TABLE … RENAME COLUMN`), refuses newer databases, closes the connection on failure.
- `llm_metrics/__main__.py`, `dashboard.py`, `seed_history.py` — the `value` key, the catalogue, and per-metric units.
- Tests: `test_latency.py` (rewritten with a controlled clock), `test_storage.py` (upgrade, atomic three-metric batch), `test_dashboard.py` (throughput label/unit/population), `test_cli.py`, `test_run_script.py`, plus the `value` key throughout.
- Docs: `README.md`, `PROJECT_STATUS.md`, `llm_metrics/README.md`, `DECISIONS.md` (D006/D017/D018/D032 revised with notes; D034, D035 added), `design-questions/09/`.

## Tests / run

- 78 tests, OK (~14 s).
- Clean `./run.sh`: `TTFT 100.3 ms`, `Total latency 181.2 ms`, `Output throughput 49.4 chunks/s` (expected 4 ÷ 0.080 s = 50), `Saved 3 observations`.
- Dashboard `?metric=output_chunks_per_s` gave n = 1 (live only); a repeated metric returned 400; `prod` exits 2.
- **Upgrade check:** a database created by the Step 008 code (version 0, `value_ms`, 170 rows) was upgraded by one CLI run to version 1 (`value`) with all rows kept.
- The screenshot review caught a bug the tests missed: y-axis labels like "100 chunks/s" were clipped at the chart edge. Fixed by putting plain numbers on the ticks plus one unit label.

## Design decisions and tradeoffs

- **Schema change, explained.** The prompt allowed reusing the observation model "if it remains correct". It didn't: `value_ms` would have stored chunks/s under a column named for milliseconds. Renaming to `value`, with the unit fixed by the metric name (D035), is the smallest correct change, and it's not a redesign. The cost was introducing migrations now (`user_version` plus one upgrade step, tested on a real version-0 file).
- **Denominator: first-to-last chunk, excluding the first chunk.** That's generation speed, independent of TTFT. Alternatives: chunks ÷ total latency mixes in queueing and prefill (TTFT), and chunks ÷ (last − first) counts N chunks over N−1 intervals, which overstates the rate.
- **Undefined means omitted, not 0 or infinity.** A zero would drag percentiles down; infinity would break them. Omitting the row is honest, and the CLI says so.
- **Empty items are not chunks.** Providers often send empty deltas; counting them would inflate throughput. TTFT still ends at the first item of any kind (unchanged semantics, D005), so in that edge case the two use different "first" moments; this is documented and tested.
- **Unit name `chunks/s`, not tokens/s.** The provider interface exposes only strings, not tokenizer tokens. A real provider must keep "non-empty stream item" semantics or use a new metric name (D034).

## Design Q&A

**Why exclude the first chunk from throughput?** The first chunk's arrival time is TTFT, which is dominated by queueing, prefill and network setup. Including it would make throughput partly a latency metric, and two providers with identical generation speed but different queueing would show different "throughput". (N−1)/(t_last − t_first) measures only the steady generation phase. *Tradeoff:* a one-chunk response has no throughput at all.

**Why rename the column instead of adding a `unit` column?** A `unit` column duplicates information that is fixed by the metric name, and allows contradictions (e.g. `ttft` in `s`). A rename is one `ALTER TABLE`. The catalogue makes the name-to-unit mapping explicit in one place. *Tradeoff:* the unit isn't self-describing in the database file; a reader needs the catalogue or docs.

**What breaks if a real provider streams multi-token or byte-sized chunks?** The number changes meaning silently. That's why the metric is named for chunks, and D034 requires a real provider to either keep "non-empty stream item" semantics or report under a new name (e.g. `output_tokens_per_s` from usage data).

## Limitations / review questions

- The rename (`measure_latency` → `measure_request`, `value_ms` → `value`) churned many files; all callers are internal.
- `latency.py` now also measures throughput; the module name is slightly narrow. I left it to avoid another rename.
- Throughput uses the same p50/p95/p99 as the latency metrics; for higher-is-better metrics the low tail matters more.
- No simulated history for total latency or throughput.
