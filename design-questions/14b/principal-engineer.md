# Step 14b — Principal engineer

**Step context:** Step 014b moved the dashboard's presentation out of Python. `dashboard.py` now returns view data (formatted values, "—" for unknown, link targets, chart coordinates) through pure `*_view` functions and `load_*_view` wrappers, and `web.py` renders it with Jinja templates in `llm_metrics/templates/` (a base layout, one template per page, and nav/chart partials). The CSS became a static file, which let the Content-Security-Policy drop `'unsafe-inline'`. Visible page text is unchanged.

**Question:** Where exactly is the line between "view data" in Python and "presentation" in templates, and why put chart geometry and number formatting on the Python side?

## Answer

The rule: Python decides what each value **means**, and the template decides where it **goes**.

- **Python (`dashboard`)** produces strings and numbers that are final for display:
  - "—" for unknown (never 0) and "unknown" instead of $0;
  - one decimal for latency and six for cost;
  - link targets that keep the other selection;
  - the success-rate wording inputs;
  - every chart coordinate: the y maximum with headroom, time-proportional x positions, the polyline, the latest point, label offsets.
- **Templates** only loop, branch on prepared booleans or None, join lists, and place values in elements.

Chart geometry stays in Python because it is a calculation whose correctness matters (proportional time axis, headroom, the latest point), and Python is where it can be read and tested. In Jinja the same arithmetic would be scattered across attribute expressions.

Number formatting stays in Python because the formats carry the project's honesty rules (unknown is not zero; failed cost is not $0). Those rules belong in one tested place, not in filters spread across templates.

`render_template` lives in `web.py`, so Jinja stays inside the web boundary like Flask. `dashboard` returns dictionaries that a JSON API could also serve.

## Critique

- **Good:** A clear, testable boundary. Templates are boring on purpose, and the dependency direction is enforced for Jinja and MarkupSafe too.
- **Weak:** `dashboard` now carries both analytics orchestration (populations, storage calls, percentiles, totals) and display wording, so it's the remaining concentration of responsibility. View dictionaries are untyped, so a key typo shows up only as an empty cell.
- **Improve:** In 014c, split query and analytics results (typed dataclasses) from view preparation. Consider `StrictUndefined` in the Jinja environment so a missing key fails a test instead of rendering empty.
