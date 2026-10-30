# Step 007 — Implementation report

Prompt: `007-time-windows.md`.

## What was implemented

- The dashboard has server-rendered links for **24h / 7d / 30d** (`/?window=`, default **7d**).
- Each window ends at the current UTC time, with bounds `now − window <= recorded_at <= now`, both inclusive.
- The count, first/latest timestamps, chart, and p50/p95/p99 (now shown with `n`) all come from the one set of rows the query returns.
- An invalid `window` returns HTTP 400 with links to the valid choices.

## Files

- `llm_metrics/storage.py` — `load_observations(..., *, start, end)` adds a parameterized `recorded_at >= ? AND recorded_at <= ?` filter.
- `llm_metrics/dashboard.py` — `WINDOWS`, `DEFAULT_WINDOW`, `parse_window()`, `window_bounds()`, `build_page(db_path, window, now)`, the window nav, the 400 page, and a chart x-axis that spans the window.
- `tests/test_dashboard.py` (rewritten around a fixed `NOW`); `tests/test_run_script.py` (assertions no longer depend on the date).
- `README.md`, `PROJECT_STATUS.md`, `DECISIONS.md`: D027 revised with a revision note, D031 added.

## Tests / run

- 62 tests, OK (~10 s).
- Clean `./run.sh` on 2026-10-30 04:36 UTC: `/` and `/?window=7d` had n = 164 (the 04:36 cutoff excludes the seeded rows from 00:00–04:00 on 10-23); `24h` had n = 20 (p99 120.1 ms, no spikes); `30d` had n = 169; `?window=bogus` returned 400.
- `APP_ENV=prod ./run.sh` still exits 2.
- No runtime artifacts or secrets staged; the bind address and CSP are unchanged (and the 400 page sends the same CSP).

## Design decisions

- **Default 7d.** Hourly data gives about 168 samples, enough for nearest-rank p99 to differ from the maximum. 24h (about 24 samples) would make p99 just the maximum.
- **Both bounds inclusive; the upper bound is `now`.** A row exactly at the cutoff counts. Future-dated rows (clock skew) are excluded rather than shown as "in the last 24h".
- **Reject, don't fall back.** An unknown value, an empty value, or a repeated `window` gets a 400. The value is never echoed, which avoids reflected-injection risk. Unrelated query parameters are ignored.
- **`build_page(db_path, window, now)`.** The handler passes the real clock; tests pass a fixed `NOW`, so no test depends on the machine clock.
- **The seed data was not changed.** Old seeded rows now fall outside the shorter windows over time, as the prompt allows.

## Design Q&A

**1. Why filter by time in the storage/query layer rather than after loading every observation?**
Correctness and cost. SQL filtering means the dashboard can only ever receive the window's rows, so no rendering code can accidentally use the full table. It also keeps memory and transfer proportional to the window, not to the whole history, which grows with every run and seed. The boundary rule lives in one place (`load_observations`), so every caller gets identical semantics.
*Tradeoff:* the filter relies on `recorded_at` being fixed-width UTC text (`...ffffffZ`), so that text order equals time order. That holds because every write goes through `format_timestamp`, but a row written by hand in another format would compare incorrectly.
*Alternative:* load everything and filter in Python. That's simpler to read, but wasteful and easy to get inconsistent. An index on `recorded_at` isn't needed at this size, but would be the next step if the table grew large.

**2. Why must the chart and the percentiles use exactly the same population?**
Because the reader interprets them together: "p99 is 472 ms" next to a chart is read as "the tallest spike on this chart". If the percentiles came from a different set (all rows, or a different window), the numbers would contradict the picture, and readers would lose trust in both. Here `render_page` receives one `observations` list and derives everything from it: count, latest, first, percentiles and polyline. A test checks that the count, `n`, the number of chart points, and p50/p95/p99 all match for each window.
*Tradeoff:* windows with few points produce coarse percentiles (with n < 100, p99 is the maximum). Showing `n` makes that visible instead of hiding it.

**3. Which clock and boundary semantics were chosen, and what would break if they were ambiguous?**
`now` is `datetime.now(timezone.utc)` at request time, and the window is `[now − d, now]`, inclusive on both ends. Stored timestamps are UTC, so there's no local-time or daylight-saving ambiguity.
If this were ambiguous: a row exactly at the cutoff could appear in one view and not another (off-by-one counts across windows); half-open versus closed intervals would make adjacent windows double-count or drop rows once windows are combined; anchoring to the *newest observation* instead of `now` would make "24h" show stale data as if it were current. That's the distortion the prompt forbids.
*Alternative:* half-open `[start, now)` is the usual choice for tiling consecutive buckets. We chose closed because there are no adjacent buckets yet, and including a row stamped exactly `now` is less surprising. Revisit when rollups or buckets arrive.

**4. Invalid input: why a 400 instead of silently showing the default?**
A silent fallback makes a typo (`?window=7D`) look like a successful request for 7d, and the page would claim a window the user didn't ask for. A 400 with links to the valid choices is explicit, safe (nothing user-supplied is reflected into the HTML), and still one click from a valid view. *Tradeoff:* it's slightly less forgiving, which is acceptable for a developer dashboard.

## Limitations / review questions

- Seeded and live rows are still mixed within a window (no source filter).
- After 2026-11-28 23:00 UTC the seeded week is outside every window, so the dashboard will show only live runs.
- The text-comparison filter depends on all timestamps going through `format_timestamp`.
- No `Host`-header check yet (DNS rebinding, noted in the design questions); out of scope here.
