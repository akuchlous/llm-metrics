# Step 014b — Move presentation from Python strings to Jinja templates

## Goal

Continue the Step 014 production-web refactor by moving the dashboard's HTML presentation out of `llm_metrics/dashboard.py` and into Jinja templates, while preserving product behavior and keeping data/query logic independent of Flask/Jinja rendering details.

Step 014a established this boundary:

```text
Browser
  ↓
llm_metrics/web.py       Flask / HTTP boundary
  ↓
llm_metrics/dashboard.py application/page logic + rendering
  ↓
llm_metrics/storage.py
```

014b should move us toward:

```text
Browser
  ↓
web.py                   Flask routes / HTTP
  ↓
dashboard.py             page/query orchestration
  ↓
storage.py               persisted facts

web/templates/           Jinja presentation
web/static/              presentation assets only if justified
```

This is **014b only**. Do not perform the broader application/analytics separation planned for 014c.

## Engineering quality requirement

Before editing code, read and follow `CODING_GUIDELINES.md`.

All changed Python must continue to follow the repository's Google-style coding standard and pass the existing style checks. Code, templates, comments, and documentation must be straightforward for both human engineers and AI coding agents to understand without reconstructing intent from Git history or chat context.

In particular:

- keep functions small and responsibilities explicit;
- use descriptive names rather than framework shorthand when clarity benefits;
- use Google-style docstrings for non-obvious Python contracts;
- comments should explain architectural reasons, security requirements, invariants, or non-obvious semantics — not narrate syntax;
- templates should use clear variable names and simple control flow;
- avoid business/analytics logic in templates;
- remove or update stale comments and user-facing references to old implementation steps;
- prefer explicit duplication of tiny presentation fragments over premature template metaprogramming, but extract genuinely shared page structure.

Passing tests is necessary but not sufficient. Review the changed code and templates for readability before committing.

## Requirements

### 1. Introduce a normal Jinja template structure

Use Flask/Jinja's standard template mechanism rather than constructing complete HTML documents in Python strings.

Create a clear template location under the package, for example:

```text
llm_metrics/
  templates/
    base.html
    dashboard.html
    requests.html
    spend.html
    invalid_query.html
```

A different small structure is acceptable if it is simpler and well justified.

Use one shared base/layout template for genuinely common document structure such as:
- HTML document shell,
- title/header,
- common navigation,
- simulated/real data labeling structure where appropriate,
- common footer or explanatory structure if currently shared.

Do not introduce a frontend framework or template abstraction layer.

### 2. Remove full-page HTML construction from Python

`dashboard.py` must no longer contain the large page-layout HTML string or full-page HTML f-string renderers.

Python should prepare facts/view data. Jinja should turn that data into markup.

It is acceptable in 014b for `dashboard.py` to continue owning:
- query validation,
- time-window selection,
- calls into storage,
- percentile calculations,
- construction of small presentation/view-model dictionaries or dataclasses.

Those concerns are separated more cleanly in 014c.

Do not move SQL into routes or templates.

### 3. Keep templates intentionally dumb

Templates may:
- loop over already-prepared rows,
- conditionally show known/unknown values,
- format simple labels supplied by Python,
- render navigation links and tables.

Templates must not:
- query storage,
- calculate percentiles,
- decide benchmark populations,
- calculate costs,
- derive reliability metrics,
- infer cache state,
- perform provider/model business logic.

If a value needs non-trivial interpretation, prepare it in Python first.

### 4. Preserve escaping and security

Use Jinja autoescaping for user/data-derived values. Do not introduce `|safe`, `Markup`, manual escaping bypasses, or equivalent unless there is a narrowly documented and tested reason.

The current Content-Security-Policy must remain effective.

Do not introduce JavaScript or external resources.

Do not expose prompts, generated responses, provider error bodies, secrets, API keys, stack traces, or other data that the current product intentionally does not expose.

### 5. CSS and presentation assets

The purpose of 014b is separation, not redesign.

Preserve the current visual appearance as closely as practical.

Move the existing CSS out of Python. Prefer either:

1. a small static stylesheet served by Flask, or
2. a shared template style block if using a static asset would unnecessarily complicate the current CSP/bootstrap behavior.

Choose the simpler maintainable option and document the decision.

If a static stylesheet is introduced, update CSP deliberately and narrowly; do not weaken it broadly.

Do not add Bootstrap, Tailwind, npm, bundlers, asset pipelines, fonts, CDNs, or frontend dependencies.

### 6. Handle the SVG chart cleanly

The aggregate dashboard currently renders an SVG chart from Python.

Do not redesign the chart in this step.

Choose a clean boundary:
- either keep the numerical chart geometry calculation in Python and render SVG markup structurally in Jinja, or
- keep a small dedicated Python SVG renderer if moving it into Jinja would make the template harder to understand.

Whichever approach is chosen:
- document why;
- do not mix chart analytics with HTML page construction;
- preserve current chart behavior;
- do not bypass Jinja escaping for arbitrary data.

### 7. Flask routes should render templates through a clean boundary

`web.py` should remain the HTTP/framework boundary.

Avoid turning route functions into page-building monoliths.

The preferred direction is conceptually:

```text
route
  ↓
parse/prepare page data
  ↓
render_template(...)
```

Whether `render_template` is called directly in `web.py` or through a very small presentation helper should be chosen based on the cleanest dependency direction. Document the choice.

Do not make benchmark collection, providers, pricing, storage, or measurement depend on Flask/Jinja.

### 8. Preserve all product behavior

Preserve the current routes and semantics:
- `/?window=&metric=`
- `/requests?data=simulated|real`
- `/spend?window=`

Preserve:
- valid/invalid query behavior;
- 200/400/404/405 behavior established in 014a;
- CSP on responses;
- TEST / SIMULATED DATA vs REAL PROVIDER DATA labeling;
- request table facts and unknown-value semantics;
- spend semantics;
- metric/window navigation;
- success/failure semantics;
- no paid calls from the dashboard.

Remove stale product copy that mentions implementation-step numbers such as "Step 010". User-facing pages should describe the product/data, not development history.

### 9. Keep `./run.sh` contract unchanged

`./run.sh` remains the one-command local path and must still:
- install/confirm pinned dependencies;
- run all tests;
- seed/use simulated data as intended;
- make one simulated benchmark attempt;
- serve the Flask dashboard locally;
- never make a paid provider call.

Do not change real-provider smoke-call semantics.

## Tests

Add or update focused tests for the template boundary.

Cover at least:
- all three primary pages render successfully through Flask;
- important page facts/labels remain present;
- valid window/metric/data navigation remains correct;
- invalid query page remains 400 and does not echo the rejected value;
- simulated and real labeling remains correct;
- request unknown values remain represented correctly;
- spend totals/population behavior remains unchanged;
- HTML-special characters in any test-controlled displayed data are escaped rather than interpreted as markup;
- no route or template triggers provider/network calls;
- CSP remains on normal and error responses;
- templates do not require global mutable state;
- app factory isolation still works;
- dependency-direction tests still guarantee Flask/Jinja do not leak into benchmark/data modules;
- `./run.sh` still works end to end.

Where existing tests assert giant exact HTML strings, prefer testing stable user-visible behavior/structure rather than preserving brittle implementation whitespace. Do not weaken tests of actual product semantics.

Run the complete test suite.

## Scope exclusions

Do **not** in 014b:
- perform the full controller/view-model/analytics separation planned for 014c;
- redesign the product UI;
- add JavaScript;
- add a frontend framework;
- add REST/JSON APIs;
- add provider/model coverage;
- add scheduling or repeated benchmarks;
- add workload matrices;
- add PostgreSQL or SQLAlchemy;
- add Gunicorn or production deployment;
- deploy to cloud;
- add authentication;
- add price scraping/history;
- change measurement, cache, cost, reliability, percentile, or provider semantics;
- make paid API calls.

## Documentation / learning workflow

Update `DECISIONS.md` with the presentation-boundary/template decision if it is not already covered by an existing decision.

Update `PROJECT_STATUS.md`, `README.md`, and `llm_metrics/README.md` where the architecture/run instructions changed.

Create `prompts/014b-output.md` describing:
- files changed;
- old vs new rendering path;
- template structure;
- CSS decision;
- SVG/chart boundary decision;
- escaping/security behavior;
- test/style results;
- what deliberately remains mixed for 014c;
- known limitations.

Create role-specific design-question material under `design-questions/14b/` following the existing workflow.

Do not modify prior numbered prompts.

Update `prompts/chatgpt-conversation.md` with a concise progress/direction entry for 014b without copying the full prompt.

## Stop condition

Before committing:

1. run the complete tests;
2. run the repository's pyink/isort/Google pylint checks;
3. run `./run.sh` through dashboard startup using simulated data only;
4. inspect the rendered dashboard, requests page, spend page, and invalid-query behavior for obvious regressions;
5. review changed Python/templates/comments for `CODING_GUIDELINES.md` compliance;
6. confirm no paid provider/API call was made.

Commit and push Step 014b, then stop.

Report the commit SHA, test count, template files created, approximate amount of HTML removed from Python, CSS/SVG boundary decisions, style-check results, and remaining 014c concerns. Do not begin 014c.