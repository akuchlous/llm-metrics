# Step 006 — Implementation report

Prompt: `006-ttft-percentiles.md`.

## What was implemented

- The dashboard shows TTFT p50/p95/p99 (nearest-rank) beneath the latest-TTFT value, computed over the same observations as the chart.
- In `APP_ENV=test`, `./run.sh` now runs the idempotent history seeder before the live measurement. It never seeds in `prod`.

## Files

- `llm_metrics/percentiles.py` (new) — `percentile(values, p)`; no HTML or storage code.
- `llm_metrics/dashboard.py` — percentile summary line; nothing shown for empty data.
- `run.sh` — seed step, guarded by `APP_ENV = test`.
- `tests/test_percentiles.py` (new), `tests/test_dashboard.py`; `tests/test_run_script.py` was reordered so `prod` runs first on a fresh copy.
- `README.md`, `PROJECT_STATUS.md`, `DECISIONS.md` (D024 and D029 reworded, D030 added).

## Tests / run

- 55 tests, OK (~8 s).
- Clean `./run.sh` (fresh `.venv` and `data/`): seeded `168 new`, measured, and served the page with `p50 101.0 ms · p95 115.8 ms · p99 472.3 ms` over 169 observations. Checked by hand: p99 is rank ⌈99·169/100⌉ = 168, the second-largest value, just below the 476.1 ms maximum.
- `APP_ENV=prod ./run.sh`: no seed output, exit 2, row count unchanged (169).
- End-to-end test: fresh-copy `prod` creates no database; then 169 → 170 rows across two test runs, and the second prints `0 new, 168 already present`; a failing test adds nothing.

## Design decisions and why

- **Nearest-rank, not interpolation.** It always reports a latency that was actually measured, needs no tie-breaking rules, and is easy to verify by hand on small datasets. Python's `statistics.quantiles` interpolates by default and requires at least two values.
- **Integer rank arithmetic** (`(p*n + 99) // 100`). Float `ceil(p/100*n)` can be off by one (`0.07*100 = 7.000000000000001`); a test covers p=7 with n=100.
- **`percentile()` raises on empty input and on p outside 1..100.** The dashboard never calls it for an empty dataset; it shows the existing "No observations yet" state instead.
- **Seeding lives in `run.sh` (orchestration)**, not in the measurement CLI, so `python -m llm_metrics` still only measures. The seeder itself refuses `prod`, a second guard behind the `run.sh` check.

## Alternatives / tradeoffs

- **Computing percentiles in SQL:** SQLite has no percentile function. A Python helper over the rows already loaded is simpler.
- **Passing precomputed percentiles into `render_page`:** cleaner separation, but more plumbing for one caller. `render_page` calls the pure function itself.
- **Tests compare visible text** (tags stripped), so styling changes won't break them.

## Limitations / review questions

- Percentiles mix the seeded week with live runs; there is no time window yet.
- With fewer than 100 observations, p99 equals the maximum (inherent to nearest-rank).
- `./run.sh` output now includes the seeder's two lines on every test-mode run.
- Not in this step's scope, but noted after Step 005: printing the page drops the label's background colour.
