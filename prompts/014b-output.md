# Step 014b — Implementation report

Prompt: `014b-jinja-templates.md`.

## Files changed

- **`llm_metrics/dashboard.py`:** no HTML left.
  - Removed: the `PAGE` layout string with inline CSS, `_page`, `_nav`, `_reliability_section`, `_chart_svg`, `_request_row` (as markup), `render_page`, `render_requests_page`, `render_spend_page`, `render_invalid_query_page`, and the `build_*` functions.
  - Added: pure view builders `aggregate_view`, `requests_view`, `spend_view`, `invalid_query_view`, plus `load_aggregate_view`, `load_requests_view`, `load_spend_view`, which read storage first. Helpers `_chart`, `_reliability`, `_metric_summary`, `_request_row`, `_spend_row`, `_spend_total` produce display-ready values.
  - Query validation (`parse_*`) and window logic are unchanged.
  - The module went from 709 to 566 lines, and from 155 lines building HTML markup to 0.
- **`llm_metrics/web.py`:**
  - New `render_page(template, view, status)` helper, used by every route.
  - Routes now read: parse → `dashboard.load_*_view` → `render_page("<page>.html", view)`.
  - Jinja `trim_blocks`/`lstrip_blocks` enabled for tidy output.
  - CSP is now `default-src 'none'; style-src 'self'`.
  - The docstring covers templates and autoescaping.
- **New `llm_metrics/templates/`:**
  - `base.html`, `aggregate.html`, `requests.html`, `spend.html`, `invalid_query.html`.
  - Partials: `_aggregate_nav.html`, `_chart.html`, `_macros.html`.
- **New `llm_metrics/static/dashboard.css`:** the CSS formerly embedded in Python, unchanged apart from grouping comments.
- **Tests:**
  - `test_dashboard.py` renders the real templates: views from `dashboard` with a fixed "now", rendered through `web.render_page` in a test request context. Its two helpers that shadowed the base class's `render` were renamed `reliability_text` and `spend_page`.
  - `test_web.py` gains tests for the stylesheet and CSP, escaping of every stored free-text field, no autoescape bypass in templates, no step numbers in product copy, isolation between two apps, and Jinja/MarkupSafe in the dependency-direction checks. The 500-response test now mocks `load_aggregate_view`.
- **Docs:**
  - `DECISIONS.md`: D058 added; D026 and D056 revised.
  - `PROJECT_STATUS.md`, `README.md`, `llm_metrics/README.md`, the 014b progress entry in `prompts/chatgpt-conversation.md`, and `design-questions/14b/` with its index row.

## Old vs new rendering path

Before (014a):

```text
route -> dashboard.parse_query -> dashboard.build_page
      -> storage reads -> render_page() f-strings + PAGE.format(...) -> HTML string -> route -> Response
```

After (014b):

```text
route -> dashboard.parse_query
      -> dashboard.load_aggregate_view -> storage reads -> aggregate_view() -> dict of display-ready values
      -> web.render_page("aggregate.html", view) -> flask.render_template (Jinja, autoescaped) -> Response
```

`dashboard` imports neither Flask nor Jinja. `web` is still the only module that imports Flask, Werkzeug, Jinja, or MarkupSafe; two tests enforce this (an AST check and a fresh-process import check).

## Template structure

| Template | Role |
|---|---|
| `base.html` | Document shell, stylesheet link, view navigation, the TEST / SIMULATED DATA vs REAL PROVIDER DATA label, `content` block |
| `aggregate.html` | Window line, success-rate section, metric summary, chart (or empty state) |
| `requests.html` | Explanations (simulated or real wording), table, empty states |
| `spend.html` | What spend is and is not, table with grand total, empty state |
| `invalid_query.html` | Valid values for every parameter (the rejected value is not in the context) |
| `_aggregate_nav.html` | Metric and window links; shared by the aggregate and invalid-query pages |
| `_chart.html` | SVG chart from precomputed coordinates |
| `_macros.html` | `nav_links(links)`: the one markup pattern repeated by four link lists |

What templates do: loop over prepared rows, branch on prepared booleans or None (`real_data`, `reliability`, `summary`, `rows`, `row.failed`), join value lists, and choose a plural "s". They never read storage, compute percentiles, costs or reliability, decide populations, infer cache state, or do arithmetic.

## CSS decision

The CSS moved to a **static file**, `llm_metrics/static/dashboard.css`, served by Flask at `/static/dashboard.css`.

A template `<style>` block would have been equally simple, but a static file let the CSP drop `'unsafe-inline'`. The policy is now `default-src 'none'; style-src 'self'`: stylesheets from this server only, no inline styles, no scripts, nothing external. That makes the CSP stricter, not looser.

Costs: one extra local request per page, and Flask's built-in static route serves `llm_metrics/static/` (which contains only the stylesheet). The SVG uses presentation attributes (`stroke`, `fill`), not `style`, so it needs no inline-style permission. A test checks the stylesheet link, the absence of `<style>`/`style=`/`<script>`, the CSS response type, and that the CSP is present without `'unsafe-inline'`.

## SVG / chart boundary decision

- **Geometry stays in Python** (`dashboard._chart`): the y-axis maximum with headroom, time-proportional x positions, polyline points, latest point, and label positions (computed there so the template needs no `left - 6`-style arithmetic).
- **`_chart.html` only places these values** in `<svg>`, `<line>`, `<text>`, `<polyline>` and `<circle>` elements. It reads as the chart's structure.
- **Why not all in Jinja:** moving the arithmetic into Jinja would hide a measurement-adjacent calculation in a template and make it harder to read and test.
- **Why not a Python SVG renderer:** that would have kept markup in Python, which this step removes.
- **Escaping:** the label and unit come from the fixed metric catalogue and are autoescaped like everything else. Coordinates are numbers formatted in Python.

## Escaping / security behavior

- **Autoescaping:** Flask enables it for `.html` templates. No template uses `|safe`, `Markup`, or `{% autoescape %}`, and a test scans every template for them (plus `<script` and `<style`).
- **Escaping test:** a stored attempt whose provider, model, workload, origin cloud and origin region are all `<script>alert("x")</script>&<b>` renders escaped on the requests and spend pages.
- **Unchanged:** the CSP on every response (including 400/404/405/500 and the stylesheet), 127.0.0.1-only serving, debug mode forced off, no stack traces in responses, and no prompts, responses, provider bodies or secrets on any page.

## Behavior check

- **Visible text unchanged:** I rendered 10 pages from the 014a code and the 014b code against the same database copy: 4 aggregate variants, simulated and real requests, 2 spend windows, and 2 invalid queries. With tags stripped, whitespace collapsed, and timestamps masked, all 10 were **identical**.
- **One deliberate copy change:** the empty simulated requests page now says "No benchmark attempts yet. Run `./run.sh` to record one." instead of also mentioning "Step 010". A test checks that no page mentions a step number.
- **Markup differences only:** links in navigation are now separated by whitespace, and the stylesheet is linked rather than inlined.

## Tests and style

- 222 tests, OK under the project venv (Python 3.13); none skipped.
- pyink, isort (google) and Google pylint report no findings for `llm_metrics`, `tests` and `scripts`.
- `./run.sh` (no `OPENAI_API_KEY`): "Dependencies ready", tests passed, one simulated attempt saved, and the dashboard served.
  - `/`, `/?window=24h&metric=output_tokens_per_s`, `/requests`, `/requests?data=real` and `/spend` returned 200 `text/html`.
  - `/static/dashboard.css` returned 200 `text/css`.
  - `/?window=bad` returned 400 and `/missing` returned 404.
- No paid API call was made.

## What deliberately remains mixed for 014c

- `dashboard.py` still owns both page/query orchestration and display wording:
  - Orchestration: which population and window, which storage calls, percentile summaries, spend totals, reliability arithmetic via `outcomes`.
  - Wording: number formats, "—"/"unknown", link targets, chart coordinates.
- Separating analytics/query results from view preparation is 014c.
- Template file names appear both in `web.py` routes and in `dashboard`'s docstring; nothing yet ties a view function to its template.

## Known limitations

- Error pages for 404/405/500 are still Flask's defaults, not the dashboard layout.
- The base layout lists the three views inline in `base.html`. Adding a page means editing that list and adding a route.
- Static files are served by Flask's development server, with no cache-busting or fingerprinting; that's fine locally and needs revisiting for deployment.
- The pages are server-rendered only: no JavaScript, auto-refresh, or interactive chart (unchanged).
- The development server is single-threaded and for local use only (unchanged from 014a).

## Design Q&A

**Why make `dashboard` return dictionaries instead of rendering templates itself?** Rendering requires Flask's Jinja environment (for `url_for` and autoescape configuration). Keeping `render_template` in `web.py` keeps every framework import in one module, so `dashboard` stays testable with plain data and reusable by a future JSON API or report generator.

**Why format numbers in Python rather than with Jinja filters?** The formats carry meaning: "—" for unknown, "unknown" instead of $0, one decimal for latency, six for cost. Putting them in Python next to the data keeps that meaning in one tested place and leaves templates free of interpretation.
