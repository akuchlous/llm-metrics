# Step 14d — Lead engineer

**Step context:** Step 014d added one versioned, read-only JSON endpoint, `GET /api/v1/metrics?metric=&window=`, that returns the aggregate page's data as facts: JSON numbers, `null` for unknown, ISO 8601 UTC times. It names its population (simulated dummy provider), metric and unit, and window; `samples` summarizes successful observations only and `reliability` counts every attempt. Shared query definitions moved from `dashboard.py` to a small `query.py`; a Flask-free `api.py` serializes analytics results; `web.py` encodes JSON and sets statuses. HTML pages are byte-identical to 014c.

**Question:** How do you know the JSON API and the HTML page report the same numbers, and that neither one quietly recalculates them?

## Answer

They share one load path and differ only in their last step:

- `query.load_aggregate_metric(db_path, window, metric, now)` is called by both `dashboard.load_aggregate_view` and `api.load_metrics_response`. It fixes the population (`query.AGGREGATE_*`) and asks `analytics.load_metric_window` for the result.
- `dashboard.aggregate_view` turns that `MetricWindow` into text; `api.metrics_response` copies its fields into a dict. Neither computes a percentile or a rate.
- Both parse the query with `query.parse_metric_query`, so valid values, defaults, and the "empty or repeated → 400" rule are the same code.

Tests make this hard to break:
- A serializer test feeds `api.metrics_response` a `MetricWindow` whose summary deliberately does not match its observations; the body must report the summary as given, which fails if the serializer starts recomputing.
- An endpoint test compares the API's percentiles with `analytics.load_metric_window` on the same database and checks the nearest-rank values by hand.
- An endpoint test checks that `/` and `/api/v1/metrics` return the same status for the same query.
- AST tests forbid `api` from importing `dashboard`, `storage`, `percentiles` or `web`, and `dashboard` from importing `api`.

## Critique

- **Good:** One load function and one parser for both consumers; drift needs a deliberate code change, not an oversight.
- **Weak:** No test compares a rendered page number with the API number for the same data; equality relies on the shared path. Percentiles are full-precision floats while the page rounds to one decimal, so a naive comparison by a reviewer would look like a mismatch.
- **Improve:** Add one cross-check test that parses the page's p95 and compares it with the API's value rounded the same way.
