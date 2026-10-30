# Step 014d — Implementation report

Prompt: `014d-versioned-json-api.md`.

## Files / modules changed

- **`llm_metrics/query.py` (new, framework-independent):** the product query definitions that the HTML dashboard and the JSON API both need, moved out of `dashboard.py`.
  - `QueryParams`, `METRICS` (the `latency.METRICS` catalogue, which also fixes units), `DEFAULT_METRIC`, `WINDOWS`, `DEFAULT_WINDOW`, `DATA`, `DEFAULT_DATA`.
  - The fixed aggregate population: `AGGREGATE_DATA` ("simulated"), `AGGREGATE_ENVIRONMENT`, `AGGREGATE_PROVIDER`, `AGGREGATE_MODEL`.
  - `parse_choice` (formerly `dashboard._parse_choice`), `parse_metric_query` (formerly `dashboard.parse_query`), `window_bounds`.
  - `load_aggregate_metric(db_path, window, metric, now)`: the single load path both consumers use.
- **`llm_metrics/api.py` (new, no Flask):** JSON API v1 representation.
  - `API_VERSION`, `timestamp(datetime)`, `metrics_response(result, window, metric)`, `load_metrics_response(...)`, `invalid_query_response()`, `error_response(code, message, **details)`.
- **`llm_metrics/dashboard.py`:** uses `query` for the shared definitions; keeps page-specific query rules (`parse_requests_query`, `parse_spend_query`, `SPEND_DEFAULT_WINDOW`, `RECENT_REQUESTS`) and all presentation. No longer imports `latency` or `providers`.
- **`llm_metrics/web.py`:** new route `/api/v1/metrics`, `json_response(body, status)`, and one `HTTPException` handler that returns JSON errors under `/api/` and Flask's default HTML errors elsewhere. Aggregate page now parses with `query.parse_metric_query`.
- **Tests:**
  - New `tests/test_api.py` (20 tests): 8 serializer tests without Flask, 12 endpoint tests through Flask's test client with a fixed clock and network blocked.
  - `tests/test_web.py`: layering test extended to `api` and `query`; `api` and `query` added to the fresh-process "loads without Flask" list and the import side-effect test; `/api/v1/metrics` added to the GET-only and no-network tests; the real-server test also fetches the API.
  - `tests/test_dashboard.py`: query tests now call `query.*` (same assertions); loop variables renamed so they don't shadow the `query` module.
- **Docs:** `DECISIONS.md` (D060; D059 annotated), `PROJECT_STATUS.md` (also restores a sentence truncated in 014c), `README.md` (new "JSON API (v1, read-only)" section, layering paragraph), `llm_metrics/README.md`, the 014d entry in `prompts/chatgpt-conversation.md`, `design-questions/14d/` and its index row.

## Final dependency direction

```text
HTML request -> web (Flask, Jinja) -> dashboard -> query -> analytics -> storage
JSON request -> web (Flask)        -> api       -> query -> analytics -> storage
```

`dashboard` and `api` also import `analytics` for its result types. Enforced by tests:

- **AST layering test:**
  - `dashboard` may not import `storage`, `api`, or `web`.
  - `api` may not import `storage`, `dashboard`, or `web`; the API test also forbids `percentiles`.
  - `query` may not import `storage`, `dashboard`, `api`, or `web`.
  - `analytics` may not import `query`, `dashboard`, `api`, or `web`.
  - `storage` imports none of them.
- **Existing tests:** only `web.py` imports Flask, Werkzeug, Jinja, or MarkupSafe. In a fresh process, `api`, `query`, `analytics`, `dashboard`, and every benchmark, provider, storage, and pricing module load without them.

## Endpoint and query contract

`GET /api/v1/metrics` (GET and HEAD only).

| Parameter | Values | Default |
|---|---|---|
| `metric` | `total_latency`, `ttft`, `output_tokens_per_s`, `output_chunks_per_s` (`query.METRICS`) | `ttft` |
| `window` | `24h`, `7d`, `30d` (`query.WINDOWS`), ending at the request time | `7d` |

Other parameters are ignored, as on the HTML page. An unknown, empty, or repeated `metric` or `window` returns 400. The rules are literally the same function (`query.parse_metric_query`) used by `/`.

## Response fields

```json
{
  "api_version": "v1",
  "population": {"data": "simulated", "provider": "dummy", "model": "dummy-model-v1"},
  "metric": {"name": "ttft", "unit": "ms"},
  "window": {"name": "24h", "start": "2026-10-29T15:46:11.206752Z", "end": "2026-10-30T15:46:11.206752Z"},
  "samples": {
    "count": 25,
    "first_recorded_at": "2026-10-29T16:00:00.000000Z",
    "latest": {"recorded_at": "2026-10-30T15:46:10.758888Z", "value": 100.40846600168152},
    "percentiles": {"p50": 100.32483400573255, "p95": 104.5, "p99": 111.6}
  },
  "reliability": {
    "attempts": 12, "successes": 12, "failures": 0,
    "success_rate": 1.0, "failure_rate": 0.0,
    "failures_by_category": {"timeout": 0, "rate_limited": 0, "provider_error": 0, "transport_error": 0, "invalid_response": 0}
  }
}
```

(Captured from the `./run.sh` dashboard.)

| Field | Type | Meaning |
|---|---|---|
| `api_version` | string | `"v1"`. |
| `population.data` | string | `"simulated"`: the dummy provider's simulated data, never real-provider data. The product word, not the storage environment name (`test`). |
| `population.provider` / `.model` | string | The measured provider/model (`dummy` / `dummy-model-v1`). |
| `metric.name` | string | The selected metric. |
| `metric.unit` | string | Unit of `samples.latest.value` and every percentile: `ms`, `tokens/s`, or `chunks/s`. |
| `window.name` | string | Selected window. |
| `window.start` / `.end` | string | Inclusive bounds (ISO 8601 UTC); `end` is the request time. |
| `samples.count` | int | Successful observations of the metric in the window. Observation, not attempt, count. |
| `samples.first_recorded_at` | string \| null | Oldest observation time. |
| `samples.latest` | object \| null | `{recorded_at, value}` of the newest observation: an observation, not a statistic. |
| `samples.percentiles` | object \| null | Derived statistics: nearest-rank `p50`, `p95`, `p99` over the same observations (always an observed value). |
| `reliability.attempts` / `.successes` / `.failures` | int | Every benchmark attempt of the population in the window, successful or failed. |
| `reliability.success_rate` / `.failure_rate` | float \| null | Fractions 0–1 of those attempts. |
| `reliability.failures_by_category` | object | Every failure category with its attempt count. |

Key order is stable and deliberate (identity first, then results). `web.json_response` uses `json.dumps(body, allow_nan=False)`, so the bytes are deterministic, and NaN or infinity would raise instead of producing invalid JSON.

## Empty and unknown semantics

- **A valid empty window is `200`:**
  - `samples` is `{"count": 0, "first_recorded_at": null, "latest": null, "percentiles": null}`.
  - With no attempts, `reliability` has counts of 0, `success_rate`/`failure_rate` of `null` (not 0% or 100%), and every category at 0.
- **Counts are always integers.** 0 is a true count. Everything that would describe a value that does not exist is `null`.
- **No display markers:** never `"—"`, `"unknown"`, `%`, or a unit in a value (tested).
- **Two populations, on purpose:** a failure counts in `reliability` but never adds a sample (no fabricated zero latency). Seeded simulated history has observations without attempt records, so `samples.count` can exceed `reliability.attempts` (25 vs 12 above). The aggregate page has the same property.

## API error semantics

Body: `{"api_version": "v1", "error": {"code": ..., "message": ...}}`, `Content-Type: application/json`.

| Case | Status | `code` | Extra fields |
|---|---|---|---|
| Invalid, empty, or repeated `metric`/`window` | 400 | `invalid_query` | `valid` (all metrics/windows), `defaults` |
| Unknown path under `/api/` | 404 | `not_found` | — |
| Non-GET method on the endpoint | 405 | `method_not_allowed` | — (the `Allow` header is kept) |
| Unhandled exception | 500 | `internal_server_error` | — (logged server-side only) |

- **No echoing or leaks:** messages are fixed text or the HTTP status name. They never contain the submitted value, an exception message, a stack trace, or any secret (tested with hostile values and a `secret-xyz` exception).
- **HTML pages unchanged:** paths outside `/api/` keep Flask's default HTML errors. The CSP header is still on every response, JSON included. It is harmless for JSON and was not weakened.

## How HTML and JSON share analytics without sharing formatting

```text
                  query.load_aggregate_metric -> analytics.load_metric_window
                 /                                      \
dashboard.aggregate_view (text, links, chart)      api.metrics_response (numbers, null, ISO)
        |                                                  |
web.render_page (Jinja)                             web.json_response
```

- **Same inputs:** both consumers parse with `query.parse_metric_query` and load with `query.load_aggregate_metric`, so they always get the same `MetricWindow` for the same query.
- **Separate outputs:** only the last step differs. The dashboard words the values for people ("100.4 ms", "—", "2026-10-30 12:00 UTC"); the API copies the natural values.
- **No dashboard dependency:** `api` never imports `dashboard`, and nothing presentational moved into `query`. Labels, links, "—", currency, and chart geometry stay in `dashboard`.

## Why these module locations

- **`api.py` as a separate module, not inside `web.py`:**
  - The prompt required testing the serializer without Flask, and the serializer carries contract decisions (`null` versus 0, two populations, time format, error bodies). Those deserve a documented home next to the compatibility note.
  - `web.py` grew only by the route, `json_response`, and the error handler. It still has no statistics or formatting.
- **`query.py` because the definitions were shared:**
  - Metrics, windows, populations, and validation became genuinely shared, and leaving them in `dashboard` would have made the API import the presentation module.
  - Putting them into `analytics` would have mixed query vocabulary into statistics.
  - The new module is about 130 lines of constants and three small functions, with no classes.

## Tests and style

- **262 tests, OK** under the project venv (Python 3.13), none skipped. That is 20 new in `test_api.py`, plus the extended web tests.
- **Prompt checklist coverage:**
  - Status codes and JSON type: 200, 400, 404, 405 and 500 are all JSON.
  - Defaults are explicit.
  - The dashboard and API use the same validation, with no echo of hostile input.
  - Identity fields are present.
  - Times match ISO 8601 `^\d{4}-…\.\d{6}Z$`, including conversion from a non-UTC offset.
  - Values are numbers, not strings.
  - Unknowns are `null`, never zero or markers.
  - Percentiles equal both a hand-computed nearest rank and `analytics.load_metric_window`.
  - Reliability counts failures, while samples hold only successes; `prod` data and other metrics are excluded.
  - An empty window and a failures-only window give truthful 200s.
  - The serializer passes analytics results through without recalculating.
  - The API does not depend on `dashboard`, `storage`, or `percentiles`.
  - No prompt, response, diagnostics, request id, workload, origin, or `OPENAI_API_KEY` value appears in any API body.
  - The CSP is kept on API responses.
  - Serialization is deterministic.
  - Network is blocked in every test.
- **HTML unchanged:** 11 HTML responses rendered by the 014c commit and by this change, against the same database copy with a fixed clock, are byte-identical, including status, CSP, and type:
  - 4 aggregate variants
  - simulated and real requests
  - 2 spend windows
  - 2 invalid queries
  - a 404
- **`./run.sh`:** "Dependencies ready" and "Tests passed", a simulated attempt saved, and the dashboard served:
  - `/`, `/requests`, `/spend`: 200 `text/html`; `/?window=bad`: 400.
  - `/api/v1/metrics` and `/api/v1/metrics?window=24h&metric=total_latency`: 200 `application/json`.
  - `?metric=x`: 400 JSON; `/api/v1/nope`: 404 JSON.
- **Style:** pyink, isort (google), and Google pylint report no findings.
- **No paid API call** was made.

## Compatibility considerations

- **What v1 commits to:** the field names, nesting, types, units, `null` meanings, time format, error `code` values, and status codes above, once anything relies on them.
- **Allowed in v1:** adding fields, error codes, or `population` values (for example `"real"` once a selector exists). Callers must ignore unknown fields.
- **Not allowed in v1:** renaming or removing a field, changing a unit or type, changing what `samples` or `reliability` count, or making a currently-`null` case 0. Any of these needs `/api/v2/`.
- **Not part of the contract:**
  - the `message` text;
  - float precision beyond what the measurement supports;
  - the order of keys (JSON objects are unordered; ours is stable, but callers shouldn't rely on it).
- **Risk:** the population is fixed today. When provider/model selection arrives, "aggregate" must keep meaning one provider/model population per response, or a new field/endpoint must express grouping.

## Known limitations / what remains after Step 014

- **One endpoint and one population:** the simulated dummy provider/model. No real-provider aggregates and no provider/model selection.
- **Not provided:** authentication, CORS (same-origin only), rate limiting, an OpenAPI/schema file, or caching headers. Served by Werkzeug's development server on 127.0.0.1 only.
- **Full-precision floats:** percentiles and values carry noise digits (e.g. `100.32483400573255`).
- **`/api` without a trailing slash** is outside the `/api/` prefix and returns the HTML 404.
- **Carried over from 014c:**
  - Untyped attempt and spend-group rows, and untyped view dictionaries (Jinja `StrictUndefined` is still a candidate).
  - Default Flask error pages for HTML.
  - No static cache-busting.
- **After 014:** decide whether any production serving/config hardening is needed before returning to product work: real-provider population selection, scheduling, deployment.

## Design Q&A

**Why not route the API through `dashboard`, since it already loads the same window?** The dashboard's outputs are strings for people. Reusing them would force the API to parse "100.4 ms" back into numbers, or tie it to presentation changes. Both consumers sit on the same `query.load_aggregate_metric` instead.

**Why separate `samples` and `reliability` objects instead of one flat summary?** They count different things: successful observations versus every attempt. Separate objects make it hard for a caller to divide one by the other or treat `samples.count` as the attempt count.
