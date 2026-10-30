# Step 005 — Implementation report

Prompt: `005-first-ttft-dashboard.md`.

## What was implemented

A local browser dashboard (`python -m llm_metrics.dashboard`, and the last stage of `./run.sh`). It shows a `TEST / SIMULATED DATA` label, provider/model, the latest TTFT, and an SVG line chart of all stored `test`/dummy/`ttft` observations.

## Files

- `llm_metrics/dashboard.py` (new) — `render_page()` (HTML + SVG), `make_server()` (`http.server` on `127.0.0.1`), `main()`.
- `llm_metrics/storage.py` — `load_observations()`: filtered, ordered read. SQL stays in this module.
- `llm_metrics/config.py` — `get_port()` (`LLM_METRICS_PORT`, default 8000).
- `run.sh` — tests → measurement → `exec` the dashboard.
- `tests/test_dashboard.py` (new), `tests/test_config.py`; `tests/test_run_script.py` was reworked because `run.sh` no longer exits on success.
- `README.md`, `PROJECT_STATUS.md`, `DECISIONS.md` (D025–D029).

## Tests / run

- 47 tests, OK (~8 s; most of it is the `run.sh` end-to-end test, which creates a venv).
- Real `./run.sh` from a fresh `.venv` printed `Dashboard: http://127.0.0.1:8000/`. `GET /` returned 200 with "All 174 observations" (168 seeded + live).
- Checked in headless Chromium at desktop and phone widths.
- Ctrl+C prints `Dashboard stopped.` and exits 0. A bad port exits 2. A busy port exits 1 with a hint instead of a traceback.
- Security scan: no runtime artifacts or secrets staged.

## Design decisions and why

- **No web dependency.** The prompt asked for the *smallest justified* dependency. Standard-library `http.server` plus a server-rendered SVG covers one static page. A package would need pip in `.venv`, which is created without it, and a network install on first run.
- **No JavaScript**, which allows a strict CSP (`default-src 'none'; style-src 'unsafe-inline'`). The page content comes from constants and from parsed timestamps and numbers, so there is little to escape. Provider and model are escaped anyway.
- **Host is a constant `127.0.0.1`**, not configurable, so the server can't be exposed by accident.
- **x-axis proportional to real time**, not to row index, so the gap between the seeded week and live runs is shown truthfully.
- **No time window in the query**, so the fixed seeded week stays visible, and the page says "All N observations, <first> to <last>", never "last 7 days".
- **The URL is printed after binding**, so `LLM_METRICS_PORT=0` works. The `run.sh` end-to-end test uses this to avoid port conflicts.

## Alternatives / tradeoffs

- **Flask or a JS chart library:** nicer interactivity, but a dependency, pip, and a network install. Rejected for now.
- **A query parameter or route for JSON data:** not required, so it was left out. The page re-reads SQLite on every request; reload to see new data.
- **The `run.sh` test now uses `Popen`:** it reads output until the `Dashboard:` line, fetches the page, then terminates. A watchdog kills it after 120 s so the suite can't hang.
- **No environment flag to skip the dashboard:** tests drive the real behaviour instead.

## Limitations / review questions

- `./run.sh` still never seeds (D024), so a fresh clone shows only the live points until `seed_history` is run once. Should `run.sh` seed automatically?
- Not verified on a real Chromebook: whether ChromeOS Chrome reaches a server bound to `127.0.0.1` inside the Linux container. The README suggests `localhost` as a fallback.
- `./run.sh` now blocks until Ctrl+C. Anything that used it as a run-and-exit command must change.
- Chart labels get small at phone width (the SVG scales down); acceptable for a local developer page.
