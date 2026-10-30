# Step 14c — Lead engineer

**Step context:** Step 014c split the dashboard's data interpretation from its presentation. New `llm_metrics/analytics.py` returns natural values (floats, ints, aware datetimes, None for unknown) for metric windows (successful observations with a nearest-rank summary, plus the success rate over all attempts), recent attempts, and real-only spend totals. `dashboard.py` keeps query semantics and turns those facts into display text, links, and chart geometry, and no longer reads storage. The direction `web → dashboard → analytics → storage` is enforced by tests, and the pages are byte-identical to before.

**Question:** How did you move logic between modules without changing a single rendered byte, and how would you catch a regression in that boundary later?

## Answer

The move was done in three moves, each checked by tests:

1. **Analytics extracted with natural values.** `load_metric_window` does what `load_aggregate_view` did before (load observations and outcome counts), but returns `Observation(recorded_at: datetime, value: float)` and a `MetricSummary` with `percentiles: {50: …}` instead of strings.
2. **View functions take analytics results.** `aggregate_view(result, window, metric)` formats exactly as before: `f"{value:.1f} {unit}"`, `"%Y-%m-%d %H:%M UTC"`, `"—"`, `"unknown"`.
3. **Templates untouched**, so any difference could come only from the data.

Evidence: 242 tests pass, including new analytics tests with no web packages and view-preparation tests that pin the exact display strings. Ten pages rendered by the 014b and 014c code against the same database, with the clock fixed, are byte-identical. A first run with the real clock differed in one chart coordinate, which turned out to be the window ending a few seconds later, not a code change.

Future regressions are caught at the layer where they happen:
- statistics in `test_analytics` (natural values, population rules);
- formatting in `ViewPreparationTest` (exact strings, "—" vs "0", "unknown" vs "$0");
- rendering and HTTP in the page and web tests;
- imports in the layering AST test.

## Critique

- **Good:** Small, mechanical steps with a byte-level equivalence check. Each test now names the layer it protects.
- **Weak:** The equivalence check was a one-off script, not a permanent test. Row dictionaries (attempts, spend groups) are still untyped, so a renamed storage column would surface only as an empty cell.
- **Improve:** Keep a small golden-HTML test per page with a fixed clock. Enable Jinja `StrictUndefined` so missing view keys fail tests.
