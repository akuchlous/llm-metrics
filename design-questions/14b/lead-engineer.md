# Step 14b — Lead engineer

**Step context:** Step 014b moved the dashboard's presentation out of Python. `dashboard.py` now returns view data (formatted values, "—" for unknown, link targets, chart coordinates) through pure `*_view` functions and `load_*_view` wrappers, and `web.py` renders it with Jinja templates in `llm_metrics/templates/` (a base layout, one template per page, and nav/chart partials). The CSS became a static file, which let the Content-Security-Policy drop `'unsafe-inline'`. Visible page text is unchanged.

**Question:** How did you prove the template migration changed nothing users see, and how do the tests keep it that way?

## Answer

Two kinds of evidence:

1. **A one-off comparison.** I rendered 10 pages (4 aggregate variants, simulated and real requests, 2 spend windows, 2 invalid queries) with the old 014a code and the new code against the same copy of the database. After stripping tags, collapsing whitespace and masking timestamps, all 10 were identical. The only intended copy change, removing "Step 010" from an empty state, appears only on an empty database.
2. **Permanent tests** that render the real templates:
   - The dashboard tests call `dashboard.load_aggregate_view(db, window, metric, NOW)` with a fixed "now" and render it through `web.render_page` in a test request context. They check behavior, not whitespace: counts, nearest-rank percentiles, chart point counts, links marked as current, "—" in exactly the unknown cells, "unknown" never $0 in spend, and population labels.
   - The web tests cover the HTTP layer, the stylesheet and CSP, escaping of hostile stored text on every page, and that no template bypasses autoescaping.

## Critique

- **Good:** Evidence before and after, with tests that assert meaning rather than exact HTML, so 014c can restructure freely. A parenthesis-matching script rewrote the test call sites, so none were missed.
- **Weak:** The visible-text comparison was a one-off script and isn't in the suite. Cell-position tests (`cells[13:15]`) are still tied to column order.
- **Improve:** Turn a small golden-text snapshot of each page into a test with masked timestamps. Look up cells by column header instead of index.
