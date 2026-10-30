# Step 14b — Director

**Step context:** Step 014b moved the dashboard's presentation out of Python. `dashboard.py` now returns view data (formatted values, "—" for unknown, link targets, chart coordinates) through pure `*_view` functions and `load_*_view` wrappers, and `web.py` renders it with Jinja templates in `llm_metrics/templates/` (a base layout, one template per page, and nav/chart partials). The CSS became a static file, which let the Content-Security-Policy drop `'unsafe-inline'`. Visible page text is unchanged.

**Question:** Users see the same pages as before. Why spend a step on this, and what does it unlock?

## Answer

It removes the main obstacle to UI work. Before, every page change meant editing Python f-strings next to data-loading code, which was slow, risky, and hard to review. Now presentation is ordinary HTML and CSS, owned separately from the data.

What it unlocks:

- **New pages at low risk:** a new view is a template plus a view function. The public Metrics site (comparisons, methodology, per-request audit pages) can be built without touching measurement or storage.
- **A security baseline suitable for a public site:** autoescaping by default, and a CSP that allows nothing inline or external.
- **A clean path to an API:** view functions return plain data, so a JSON endpoint can reuse them.

It also kept the promise of the 014 sequence: each substep changes one layer, with evidence that nothing else moved (identical visible text across 10 pages, 222 tests).

## Critique

- **Good:** Low-risk, reviewable progress toward a product UI. Security got stricter as a side effect rather than costing extra.
- **Weak:** Three steps of web refactoring with no visible user change. The pressure to show product value is growing.
- **Improve:** Keep 014c tightly scoped, then switch to visible product work: real provider coverage and a public methodology page built on these templates.
