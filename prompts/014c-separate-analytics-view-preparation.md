# Step 014c — Separate analytics/query orchestration from view preparation

## Goal

Continue the Step 014 production-web refactor by separating **measurement/application analytics** from **presentation-specific view preparation**.

Step 014b successfully removed HTML/CSS generation from Python and moved presentation markup into Jinja templates. However, `llm_metrics/dashboard.py` still mixes two different responsibilities:

1. deciding what data population to load and computing product/analytics results; and
2. converting those results into display-specific strings, navigation links, chart coordinates, and template-ready dictionaries.

014c should create a clear boundary between those responsibilities without changing product behavior, metric semantics, storage schema, routes, or visible page meaning.

This is **014c only**. Keep the refactor small and reviewable.

## Engineering quality requirement

Before editing code, read and follow `CODING_GUIDELINES.md`.

Treat the Google Python Style Guide as the primary style reference where it fits this repository. Produce code that is straightforward for both human engineers and AI coding agents to understand and modify safely.

In particular:

- use descriptive names and small, single-responsibility functions;
- keep module ownership and dependency direction explicit;
- use concise Google-style docstrings for non-obvious contracts;
- comments should explain non-obvious **why**, invariants, population semantics, or architectural boundaries rather than narrating syntax;
- remove/update stale comments and docstrings created by moving responsibilities;
- avoid generic framework abstractions, base classes, registries, service containers, or dependency-injection machinery that this product does not need;
- prefer plain Python data and explicit function calls.

Passing tests is necessary but not sufficient. Review changed code for readability and architectural clarity before committing.

## Current state

After 014b the effective request path is approximately:

```text
Flask route
    ↓
dashboard.parse_*
    ↓
dashboard.load_*_view
    ↓
storage + analytics calculations + formatting/link/chart preparation
    ↓
Jinja template
```

`dashboard.py` contains both analytics/orchestration and presentation preparation. Examples include:

- `window_bounds`, population selection, storage reads, outcome counts, percentile computation, spend aggregation;
- `_number`, `_money`, `_text`, `_origin`, `_layout`, navigation-link construction, display timestamps, chart SVG coordinates, and row dictionaries.

The target direction is:

```text
Flask routes
    ↓
application / analytics
    ↓
storage

application / analytics result
    ↓
view preparation
    ↓
Jinja templates
```

A concrete small-module shape is preferred, for example:

```text
llm_metrics/
    analytics.py       # page-independent/query-independent product analytics
    dashboard.py       # dashboard query semantics + view preparation
    web.py             # Flask HTTP + Jinja rendering
```

or another similarly simple structure if the existing code makes a slightly different split clearer.

Do **not** create layers merely to match these names. The important requirement is the responsibility boundary.

## Core design rule

The analytics/application side should return **typed/plain facts with their natural values**, not strings formatted for HTML.

For example, analytics should prefer concepts such as:

```text
success_rate = 0.995
latest_value = 812.4
percentiles = {50: ..., 95: ..., 99: ...}
total_cost = 0.001234
recorded_at = timestamp
```

rather than presentation forms such as:

```text
"99.5"
"812.4 ms"
"$0.001234"
"—"
"unknown"
"2026-10-30 12:34 UTC"
```

The presentation/view layer owns the latter.

This distinction is important because the same analytics results should later be reusable by a JSON API, use-case recommendation layer, report generator, or other consumer without parsing human-facing strings.

## Requirements

### 1. Extract reusable analytics/application results

Move the non-presentation computation currently embedded in `dashboard.py` into a small framework-independent module or modules.

At minimum, examine and separate the logic for:

- window bounds;
- aggregate metric population loading;
- observed success/failure results;
- metric summary inputs/results including latest value and nearest-rank percentiles;
- recent request loading/population selection where appropriate;
- spend loading and totals.

Do not move SQL out of `storage.py`. Analytics/application code should call storage APIs, not duplicate SQL.

Do not change the statistical semantics established by earlier steps.

### 2. Preserve population semantics explicitly

The code must remain clear that:

- observed success/failure rate uses **all benchmark attempts** in the selected population/window;
- latency/throughput percentile distributions use successful metric observations only;
- failed attempts must not become fabricated zero latency/throughput samples;
- simulated and real populations remain separated;
- spend remains real-provider benchmark API spend and known costs retain their existing semantics.

These rules should be obvious from function/module contracts and tests, not dependent on remembering prior conversations.

### 3. Keep presentation-specific work in the dashboard/view layer

Presentation/view preparation should continue to own things such as:

- `"—"` versus `"unknown"` display choices;
- decimal formatting and currency formatting;
- human-readable timestamps;
- navigation/link dictionaries;
- page labels and wording-oriented flags;
- chart SVG geometry if it is specifically for the current dashboard presentation;
- conversion from analytics facts to template-ready dictionaries.

Do not push presentation formatting into `storage.py` or the reusable analytics layer.

### 4. Keep templates dumb

Preserve the 014b rule: templates render already-prepared presentation values.

Do not move analytics, arithmetic, percentile calculation, cost calculation, population decisions, cache inference, or storage access into Jinja.

Preserve autoescaping and the existing prohibition on `|safe`, `Markup`, autoescape disabling, inline scripts, and inline styles.

### 5. Keep Flask at the boundary

`web.py` should remain responsible for:

- Flask application creation;
- HTTP routing;
- query extraction;
- response/status construction;
- Jinja rendering;
- security headers;
- local serving.

Benchmark/provider/measurement/storage/analytics code must remain usable without importing Flask, Werkzeug, Jinja, or MarkupSafe.

Do not introduce Flask context dependencies into analytics or view-building functions merely for `url_for`; explicit small link construction is acceptable at this stage.

### 6. Preserve current behavior

Do not intentionally change:

- routes (`/`, `/requests`, `/spend`);
- valid/invalid query semantics;
- 200/400/404/405/500 behavior;
- visible product meaning;
- simulated/real labels;
- CSP/security behavior;
- chart semantics;
- percentile method;
- reliability semantics;
- cost semantics;
- request traceability;
- cache/workload/origin semantics;
- database schema;
- paid-call boundaries.

Minor whitespace/markup differences are acceptable if they do not change visible meaning.

### 7. Avoid premature domain modeling

Do not create a large hierarchy of classes or DTOs just because analytics and views are being separated.

Plain dictionaries, tuples, dataclasses, or named structures are all acceptable when they improve clarity. Choose the smallest representation that makes invalid/misleading states harder to create and makes field meaning clear.

If dictionaries become ambiguous across the new boundary, a small frozen dataclass may be justified. If dictionaries remain obvious and tested, keep them.

Document the reasoning in the output report.

## Tests

Add or reorganize tests so the new boundary is independently testable.

Cover at least:

1. analytics/application functions can be tested without Flask/Jinja;
2. analytics results contain natural/raw values rather than HTML/display-formatted strings where that distinction matters;
3. reliability population includes failures while metric percentile population excludes them;
4. percentile results remain nearest-rank and unchanged;
5. empty populations remain well-defined;
6. spend totals preserve known/unknown-cost semantics;
7. view preparation converts analytics facts to the same human-facing formatting as 014b;
8. request rows preserve unknown-versus-zero distinctions;
9. existing route/template behavior remains covered through Flask's test client;
10. templates remain free of business calculations and unsafe escaping bypasses;
11. no benchmark/provider network calls occur in tests;
12. dependency-direction tests confirm Flask/Jinja do not leak into analytics, storage, providers, measurement, or pricing;
13. `./run.sh` remains the simulated one-command path and makes no paid provider request.

Preserve all existing tests unless a test is specifically moved to a more appropriate layer. Do not weaken assertions merely to make the refactor pass.

## Documentation / learning workflow

Update `DECISIONS.md` with the analytics-versus-presentation boundary if it is not already adequately recorded.

Update `PROJECT_STATUS.md` to current truth.

Update relevant README architecture descriptions.

Create:

`prompts/014c-output.md`

The report should describe:

- files/modules changed;
- responsibility boundary before and after;
- dependency direction;
- which values remain raw analytics facts and which are presentation formatting;
- whether dictionaries or dataclasses were chosen and why;
- test/style results;
- known limitations and what deliberately remains for 014d.

Create role-specific design-question material under `design-questions/14c/` following the existing workflow.

Do not modify prior numbered prompts.

## Scope exclusions

Do **not** in 014c:

- redesign the UI;
- add new product metrics;
- add a public JSON/REST API yet;
- add provider/model coverage;
- add workload matrices or use-case recommendations;
- add scheduling;
- add PostgreSQL or SQLAlchemy;
- add Redis, queues, Kafka, or caches;
- add Gunicorn or cloud deployment;
- add authentication;
- add price scraping/history;
- change cache methodology;
- change Step 013 measurement semantics;
- add frontend JavaScript/frameworks;
- make paid API calls.

## Stop condition

Run the complete test suite, formatting/style checks, and `./run.sh` simulated path.

Before committing, review changed Python against `CODING_GUIDELINES.md`, especially whether a human engineer or AI coding agent can identify the owner of:

- raw benchmark facts;
- analytics/statistical interpretation;
- presentation formatting;
- HTTP/Jinja rendering.

There should be a simple answer for each.

Commit and push Step 014c, then stop. Do not begin 014d.

Report the commit SHA, files/modules introduced or reorganized, test count, style-check result, dependency-boundary result, and remaining limitations.