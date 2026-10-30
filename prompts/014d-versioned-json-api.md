# Step 014d — Establish a small versioned read-only JSON API

## Goal

Complete the next small part of the Step 014 production-web refactor by proving that the reusable analytics layer created in 014c can serve a **machine-readable consumer** in addition to the HTML dashboard.

Add a deliberately small, versioned, read-only JSON API for aggregate metric results. This is the first public-interface shape for LLM Metrics, not a complete REST API redesign.

The main architectural proof should be:

```text
                    analytics
                   /         \
          dashboard/view     JSON API
                |               |
              Jinja            HTTP
                \               /
                     web
```

The HTML dashboard and JSON API should consume the same analytics semantics rather than independently reimplementing percentiles, reliability, population rules, or storage queries.

This is **014d only**. Keep the interface intentionally narrow and reviewable.

## Prerequisite / review context

Step 014c is complete and reviewed. Its intended dependency direction is:

```text
web -> dashboard -> analytics -> storage
```

`llm_metrics/analytics.py` now owns reusable product analytics and returns natural values such as floats, integers, aware datetimes, and `None` for unknown facts. `dashboard.py` owns presentation formatting and template-ready view data. Preserve that separation.

Before editing code, read:

- `CODING_GUIDELINES.md`
- `prompts/014c-output.md`
- relevant architecture decisions in `DECISIONS.md`

## Engineering quality requirement

Follow `CODING_GUIDELINES.md` and Google Python style where appropriate.

Prefer:

- explicit, small functions;
- stable and documented response semantics;
- natural machine-readable values;
- deterministic serialization;
- one obvious owner for each transformation;
- focused tests at the analytics/API boundary.

Avoid:

- generic REST frameworks or API abstraction layers;
- schema-generation packages;
- service containers, repositories, controllers, or DTO hierarchies added only for architectural appearance;
- speculative endpoints for future Router/Exchange needs;
- duplicating analytics calculations in HTTP code.

Passing tests is necessary but not sufficient. Review the changed code for API clarity and backward-compatibility implications before committing.

## Product/API principle

The JSON API is a product interface, not an HTML representation converted to JSON.

It must expose **facts**, not presentation strings.

Good examples:

```json
{
  "success_rate": 0.995,
  "sample_count": 423,
  "latest_value": 812.4,
  "percentiles": {
    "50": 410.2,
    "95": 812.4,
    "99": 1105.7
  }
}
```

Avoid values such as:

```json
{
  "success_rate": "99.5%",
  "p95": "812.4 ms",
  "cost": "$0.001234",
  "unknown_value": "—"
}
```

JSON `null` represents an unknown/not-applicable fact where appropriate. Do not convert unknowns to zero.

## Scope: one aggregate endpoint

Add exactly one primary v1 analytics endpoint:

```text
GET /api/v1/metrics
```

Do not add a broad endpoint collection in this step.

The endpoint should expose one aggregate metric window using the same analytics semantics as the current aggregate dashboard.

### Query parameters

Support explicit query parameters for the dimensions the current aggregate analytics can honestly serve.

At minimum:

```text
metric=<metric-name>
window=24h|7d|30d
```

Use the existing valid metric catalogue and window definitions rather than creating a second independent catalogue.

For this step, it is acceptable for the aggregate population to remain the same simulated dummy provider/model population used by the current aggregate dashboard. Do **not** pretend arbitrary real provider/model selection exists if the analytics/storage path does not yet support a coherent public selector.

The response must explicitly identify the population so a caller cannot mistake simulated results for real-provider measurements.

Do not silently mix simulated and real data.

## Response contract

Design a small explicit response shape. It should contain enough context that a result remains interpretable outside the website.

At minimum include concepts equivalent to:

```text
api_version
population/environment
provider
model
metric
metric unit
window name
window start/end
sample count
latest observation/value when available
percentiles p50/p95/p99 when available
observed reliability over all attempts
```

Reliability should preserve the existing population semantics:

- success/failure rate counts all attempts in the selected population/window;
- metric sample count and percentiles use successful observations only;
- failures never become zero-valued latency/throughput samples.

Where useful, include counts such as total attempts, successes, failures and failures by category so the rate is auditable.

Do not add invented confidence scores, rankings, recommendations, SLA claims, provider uptime claims, or quality scores.

### Time serialization

Serialize timestamps in a standard machine-readable UTC representation (ISO 8601). Choose one consistent convention and test it.

Do not use dashboard display strings such as `"2026-10-30 12:34 UTC"` in the JSON contract.

### Empty data

An empty but valid population/window is not necessarily an HTTP error.

Return a valid JSON response whose metric summary fields are `null`/empty as appropriate and whose counts/reliability truthfully describe the absence of samples.

Do not fabricate zeros where zero would mean an observed measurement.

## HTTP behavior

Use normal JSON response semantics:

- `200` for a valid query, including a valid empty result;
- `400` for invalid/repeated/empty supported query parameters;
- `404` for unknown routes;
- JSON `Content-Type` for API responses.

API errors for this endpoint should be machine-readable JSON and must not echo hostile/rejected query values, stack traces, prompts, responses, provider error bodies, secrets, or API keys.

A small shape such as an error code/message is sufficient. Do not build a general error framework.

Preserve the existing HTML error behavior for the existing HTML pages unless a tiny shared change is clearly necessary.

## API versioning

The `/api/v1/` prefix is intentional.

Document that once this endpoint is treated as public, its field meanings and types form a compatibility contract. Future additive fields are generally easier than silently changing/removing existing fields or changing units/types.

Do not implement multiple versions, content negotiation, deprecation machinery, OpenAPI generation, or compatibility adapters now.

## Code organization

Keep the existing architecture understandable.

A preferred dependency shape is:

```text
HTML request -> web -> dashboard -> analytics -> storage
JSON request -> web -> API serialization -> analytics -> storage
```

A tiny framework-independent serialization/helper module such as `api.py` is acceptable if it materially clarifies the boundary. It should transform analytics results into JSON-ready natural structures and must not import Flask/Jinja.

Alternatively, a very small serializer in `web.py` is acceptable if it stays obviously HTTP/serialization-only and does not duplicate analytics or grow the module materially.

Choose the simpler option based on the actual code. Explain the choice in `014d-output.md`.

Do not route the JSON API through `dashboard.py` merely to reuse human formatting. The API should consume analytics facts directly.

Do not allow API code to call `storage` directly if the same result is already represented by the analytics layer.

## Reuse query semantics without coupling API to presentation

Avoid duplicating the meaning of `24h`, `7d`, `30d`, metric names, or their units in multiple inconsistent places.

If constants/query-validation concepts currently live in `dashboard.py` but are now legitimately shared by HTML and API consumers, move only the genuinely shared product/query concepts to the smallest sensible framework-independent location.

Do not move navigation links, page labels, `"—"`, currency formatting, chart geometry, or other presentation concerns into a shared API module.

The resulting ownership should be obvious:

- storage: persisted facts / SQL;
- analytics: population/statistical interpretation;
- shared query/product definitions if needed: valid product selections and units;
- dashboard: human presentation;
- API serializer: machine representation;
- web: HTTP boundary.

## Security and privacy

Preserve all existing privacy constraints.

The JSON endpoint must not expose:

- prompts;
- generated responses;
- API keys;
- raw provider error bodies;
- stack traces;
- internal secrets.

Do not add CORS broadly in this step. Same-origin access is sufficient for now.

Do not add authentication yet.

Preserve existing security headers where applicable. If CSP is irrelevant to JSON responses, do not weaken the HTML CSP merely for the API.

## Tests

Add focused tests covering at least:

1. `GET /api/v1/metrics` returns `200` and JSON for a valid query;
2. default metric/window behavior is explicit and tested if defaults are supported;
3. `metric` and `window` validation uses the same product definitions as the HTML dashboard;
4. invalid, empty, and repeated supported query parameters return `400` JSON without echoing submitted values;
5. response identifies `api_version`, simulated environment/population, provider, model, metric, unit, and selected window;
6. timestamps are consistent ISO 8601 UTC strings;
7. numeric facts remain JSON numbers, not display strings;
8. unknown facts are JSON `null`, not zero, `"—"`, or `"unknown"`;
9. p50/p95/p99 match the existing nearest-rank analytics result;
10. reliability counts all attempts while metric samples include successful observations only;
11. valid empty data returns a truthful `200` response;
12. API serialization consumes analytics results and does not recalculate percentiles/reliability;
13. API code does not depend on `dashboard` display formatting;
14. no API path exposes prompts/responses/secrets/raw provider errors;
15. existing HTML routes remain behaviorally unchanged;
16. dependency-direction tests remain/enhance protection against Flask/Jinja leaking into analytics/storage/provider/measurement modules;
17. no network or paid provider calls occur in tests;
18. `./run.sh` remains simulated/offline and working.

If a framework-independent API serializer is added, test it directly without Flask as well as through Flask's test client.

Do not weaken existing assertions to make the new endpoint pass.

## Documentation / learning workflow

Update `DECISIONS.md` with the small versioned read-only API decision and compatibility principle.

Update `PROJECT_STATUS.md` to current truth.

Update relevant README architecture/API documentation.

Create:

`prompts/014d-output.md`

The report should describe:

- files/modules changed;
- final dependency direction;
- exact endpoint/query contract;
- exact response field meanings/types;
- empty/unknown semantics;
- API error semantics;
- how HTML and JSON reuse the same analytics without sharing presentation formatting;
- why the chosen serializer/module location is appropriately small;
- tests/style results;
- compatibility considerations;
- known limitations and what remains after Step 014.

Create role-specific design-question material under `design-questions/14d/` following the existing workflow.

Do not modify prior numbered prompts.

## Scope exclusions

Do **not** in 014d:

- add `/api/v1/providers`, `/api/v1/requests`, `/api/v1/spend`, or other endpoint families;
- expose arbitrary provider/model selection before population semantics are designed;
- add Router or Exchange functionality;
- add use-case recommendations/rankings;
- add new benchmark metrics;
- add new providers/models;
- add scheduling;
- add workload matrices;
- add PostgreSQL or SQLAlchemy;
- add Redis/queues/Kafka/caches;
- add authentication or API keys;
- add CORS broadly;
- add rate limiting;
- add OpenAPI/Swagger/schema-generation dependencies;
- add Gunicorn/cloud deployment;
- add price scraping/history;
- redesign the UI;
- add frontend JavaScript/frameworks;
- change Step 013 measurement/cache semantics;
- make paid API calls.

## Stop condition

Run the complete test suite, formatting/style checks, and `./run.sh` simulated path.

Before committing, review the endpoint as if an independent future Router team were going to consume it. A caller should be able to understand:

- exactly which population was measured;
- exactly which time window and metric were requested;
- which values are observations versus derived statistics;
- which population reliability uses;
- what `null` means;
- what units apply;
- which parts of the response can reasonably be treated as a v1 compatibility contract.

Commit and push Step 014d, then stop.

Do not begin provider expansion, scheduling, deployment, PostgreSQL, or Router work.

Report the commit SHA, endpoint added, response shape, test count, style/dependency results, and remaining limitations.