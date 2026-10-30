# Step 05 — Lead engineer

**Step context:** Step 005 added a stdlib-only local dashboard on `127.0.0.1` (HTML + server-rendered SVG chart, no JavaScript), started at the end of `./run.sh`.

**Question:** Why standard-library `http.server` and a server-rendered SVG instead of Flask plus a JS charting library?

## Answer

The prompt asked for the smallest *justified* dependency, and none was justified. One read-only page needs a GET handler, an HTML template and a line chart. Any package would also force pip into a venv deliberately created without it (D012), plus a network install on the first `./run.sh`.

So: `http.server` serves `/` (and 404s for everything else); `load_observations()` reads from SQLite (SQL stays in `storage.py`); `render_page()` returns HTML with an SVG polyline, whose x-axis is proportional to real time, so the gap between the seeded week and live runs is truthful. No JavaScript means a strict CSP is possible. The rendering functions are pure, so tests check them without a browser, and one test starts a real server on port 0.

## Critique

- **Good:** About 180 lines, zero dependencies, fully testable without a browser, and confirmed working on the owner's Chromebook.
- **Weak:** No interactivity (no tooltips, zoom or live refresh). Hand-rolled chart code grows quickly once there are multiple series, ticks or legends, and it's easy to get axis maths subtly wrong.
- **Improve:** Define the exit criterion now: when a chart needs interaction or more than one series, vendor a small, pinned JS chart library (keeping the CSP, with no CDN). Keep rendering isolated so the swap only touches `dashboard.py`.
