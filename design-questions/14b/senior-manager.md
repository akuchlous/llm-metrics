# Step 14b — Senior manager

**Step context:** Step 014b moved the dashboard's presentation out of Python. `dashboard.py` now returns view data (formatted values, "—" for unknown, link targets, chart coordinates) through pure `*_view` functions and `load_*_view` wrappers, and `web.py` renders it with Jinja templates in `llm_metrics/templates/` (a base layout, one template per page, and nav/chart partials). The CSS became a static file, which let the Content-Security-Policy drop `'unsafe-inline'`. Visible page text is unchanged.

**Question:** What did moving HTML into templates change for security and for the people who will maintain the UI?

## Answer

**Security:**

- **Escaping by default:** escaping is now Jinja's job for every value, instead of an `html.escape` call each developer had to remember. No template may use `|safe`, `Markup`, or `{% autoescape %}`; a test scans every template for them, and another renders a stored attempt full of HTML-special characters and checks it comes out escaped.
- **Stricter CSP:** moving the CSS into a file let the CSP drop `'unsafe-inline'`. The browser now refuses any inline style or script, not just external ones.

**Maintainability:** a designer or front-end engineer can edit layout and copy in `.html` and `.css` files without touching Python, and a Python change to analytics can't accidentally break markup. Every template starts with a comment listing its context, so an engineer or an AI agent can see which values are available without reading the Python.

**Product copy:** user-facing pages no longer mention development history ("Step 010"), and a test keeps it that way.

## Critique

- **Good:** It's safer by construction, the security rules are encoded as tests rather than conventions, and the work splits more cleanly between Python and UI changes.
- **Weak:** There's no visual regression check: a CSS edit could break the layout and no test would notice. Error pages (404/500) still don't use the dashboard look.
- **Improve:** Add a lightweight screenshot or HTML snapshot review to the release checklist. Give error pages the shared layout when the UI work starts.
