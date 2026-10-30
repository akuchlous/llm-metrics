# Step 014c — Implementation report

Prompt: `014c-separate-analytics-view-preparation.md`.

## Files / modules changed

- **`llm_metrics/analytics.py` (new):** framework-independent product analytics, returning natural values.
  - `window_bounds(duration, now)`
  - `parse_recorded_at`
  - `summarize_metric(observations)`: nearest-rank `MetricSummary`, or None
  - `load_metric_window(...)`: a `MetricWindow` with successful observations, their summary, and the success rate over all attempts
  - `load_recent_attempts(...)`
  - `spend_totals(groups)` and `load_benchmark_spend(...)` (real environment only)
  - Frozen dataclasses: `Observation`, `MetricSummary`, `MetricWindow`, `SpendTotals`, `Spend`
  - Constants: `SIMULATED_ENVIRONMENT`, `REAL_ENVIRONMENT`, `PERCENTILES`
- **`llm_metrics/dashboard.py` (reorganized):** query semantics plus view preparation.
  - Same query rules: `parse_*`, window names, `DATA`.
  - `window_bounds(window, now)` maps a window name to a duration and delegates to analytics.
  - `aggregate_view(result, window, metric)` and `spend_view(spend, window)` now take analytics results. `requests_view(attempts, data)` takes analytics' attempts.
  - `load_*_view` functions call `analytics` instead of `storage`.
  - All formatting stays here: `_number`, `_money`, `_percent`, `_text`, `_origin`, `_display_time`, `_layout`, `_link`, `_aggregate_links`, and `_chart` (SVG geometry).
  - It no longer imports `storage` or `percentiles`.
- **`llm_metrics/web.py`:** docstring only; the layering description now includes analytics. Routes are unchanged.
- **Tests:**
  - New `tests/test_analytics.py` (15 tests, no Flask or Jinja).
  - `tests/test_dashboard.py`: the four spots that build views directly now pass analytics results. New `ViewPreparationTest` (4 tests) checks the facts-to-display conversion without rendering.
  - `tests/test_web.py`: new layering test; `analytics` added to the fresh-process "loads without Flask" list.
- **Docs:**
  - `DECISIONS.md`: D059 added; D056 and D058 revised.
  - `PROJECT_STATUS.md`, `README.md` (layering sentence), `llm_metrics/README.md`, the 014c entry in `prompts/chatgpt-conversation.md`, and `design-questions/14c/` with its index row.

## Responsibility boundary

| Concern | Before (014b) | After (014c) |
|---|---|---|
| Raw benchmark facts (SQL, schema) | `storage` | `storage` (unchanged) |
| Population and window interpretation, success rate, percentiles, spend totals | `dashboard` (mixed with formatting) | `analytics` |
| Query semantics (valid values, window names, which population a page shows) | `dashboard` | `dashboard` |
| Display formatting, "—"/"unknown", UTC labels, links, labels, chart geometry | `dashboard` | `dashboard` |
| HTTP, Jinja rendering, security headers, serving | `web` | `web` |
| Markup | templates | templates (unchanged) |

Where each thing now lives:
- **Raw benchmark facts:** `storage`.
- **Statistical interpretation:** `analytics`.
- **Presentation formatting:** `dashboard`.
- **HTTP and Jinja rendering:** `web`.

## Dependency direction

```text
web (Flask, Jinja) -> dashboard -> analytics -> storage
```

Enforced by tests:
- **AST layering test:** `dashboard` may not import `storage` or `web`; `analytics` may not import `dashboard` or `web`; `storage` imports none of them.
- **Existing AST test:** only `web.py` imports Flask, Werkzeug, Jinja or MarkupSafe.
- **Fresh-process tests:** `analytics`, `dashboard`, and every benchmark, provider, storage and pricing module load without any of those packages.

## Raw facts vs presentation formatting

Analytics returns, and dashboard formats:

| Fact | Analytics value | Dashboard display |
|---|---|---|
| Observation time | `datetime` (aware UTC) | `"2026-11-30 11:00 UTC"` |
| Latest value / percentiles | `float`, `{50: 100.0, 95: …}` | `"123.5 ms"`, `[{"name": "p50", "value": "100.0 ms"}]` |
| Success / failure rate | `0.75` / `0.25` (from `outcomes.success_rate`) | `"75.0"` / `"25.0"` |
| Unknown token/cost/latency | `None` | `"—"` |
| Unknown spend cost | `total_cost=None` | `"unknown"` (never `$0`) |
| Known spend cost | `0.0000285` | `"$0.000029"` |
| Cached input tokens reported as zero | `0` | `"0"` (distinct from `"—"`) |
| Window | `(start, end)` datetimes | `{"start": "… UTC", "end": "… UTC"}` |
| Observations for the chart | `Observation` tuples | SVG coordinates (`_chart`, dashboard-specific) |

**Population semantics** are stated in `analytics`' module and function contracts and tested there:
- Success rates count every attempt.
- `MetricWindow.observations` and `summary` hold successful observations only, so there are no fabricated zeros.
- Environments are never mixed.
- `load_benchmark_spend` is fixed to the real environment and keeps unknown cost as None.

## Dictionaries vs dataclasses

**Frozen dataclasses for new structures that cross the boundary:** `Observation`, `MetricSummary`, `MetricWindow`, `SpendTotals`, `Spend`. Each field's meaning matters and was easy to confuse as dictionary keys:
- `MetricWindow` deliberately holds two populations: successful `observations` and the all-attempts `reliability`. Named fields make that explicit.
- `SpendTotals.total_cost: float | None` documents that None means unknown, not $0.
- Being frozen, they can't be mutated by a view step.

**Kept as dictionaries:**
- `outcomes.success_rate`'s result: an existing, tested API with clear keys, also used by the success-rate tests.
- Storage rows for recent attempts and spend groups: natural values already, with keys defined by the schema. Wrapping them would have duplicated the column list without adding safety.

No base classes, registries or service objects.

## Behavior

- Routes, query semantics, statuses, CSP, labels, percentiles, reliability, cost, cache, workload, origin, schema, and paid-call boundaries are unchanged. The templates are unchanged.
- **Proof:** I rendered 10 pages (4 aggregate variants, simulated and real requests, 2 spend windows, 2 invalid queries) with the 014b code and the 014c code against the same database copy, with the clock fixed. The raw HTML, status codes and CSP headers were **byte-identical**.
  - A first comparison using the real clock differed in one chart coordinate (665.5 vs 665.4), because the window ended a few seconds later in the second run. Fixing the clock removed it.

## Tests and style

- 242 tests, OK under the project venv (Python 3.13); none skipped.
- **New analytics tests** (no web packages):
  - Window bounds and timestamp parsing.
  - Nearest-rank percentiles on unsorted input, a single observation, and natural-value types.
  - Reliability includes failures while the distribution excludes them (no zero values).
  - Empty windows give None summary and rate.
  - Population and window filtering.
  - Recent attempts stay separate per environment, with unknowns as None and cached tokens 0 vs None.
  - Spend totals sum known costs only; unknown cost is None; spend is real-only; empty spend is handled.
  - `analytics` imports no web package.
- **New view-preparation tests:** aggregate, empty aggregate, request row (unknown vs zero), and spend view wording.
- **Unchanged tests:** route, template, escaping, CSP, dependency, installer, measurement, storage, cache and provider tests.
- `./run.sh` (no `OPENAI_API_KEY`): "Dependencies ready", tests passed, one simulated attempt saved, and the dashboard served `/`, `/requests`, `/requests?data=real` and `/spend` with 200 and `/?window=bad` with 400.
- pyink, isort (google) and Google pylint report no findings.
- No paid API call was made.

## Known limitations / what remains for 014d

- **Untyped row dicts:** recent-attempt and spend-group rows cross the analytics boundary as storage dicts, natural values but untyped. View dicts are untyped too, so a mistyped key renders as an empty cell instead of failing. Options for later: typed rows, or Jinja `StrictUndefined`.
- **No other consumer yet:** `analytics` has only one consumer. Its API shape is proven only by the dashboard and the tests until a JSON API or report uses it (deliberately not added here).
- **Page populations are fixed in `dashboard`:** the aggregate page is still fixed to the simulated dummy population. Real-provider aggregate views will need provider/model selection.
- **Unchanged from 014b:** default Flask error pages, no static cache-busting, the development server only, and template names that appear in both `web.py` and `dashboard` docs.

## Design Q&A

**Why did the dashboard lose its storage import instead of keeping it for "simple" reads like recent requests?** A single rule ("the dashboard reads data only through analytics") is easy to state, test and keep. Mixed access would make every new page a judgment call about which layer to read from.

**Why keep chart geometry in the dashboard and not in analytics?** It depends on this page's SVG size and margins, so it isn't a fact about the benchmark. Another consumer (an API, a report) wants the observations themselves, which `MetricWindow.observations` provides.
