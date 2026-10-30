# Step 14a — Lead engineer

**Step context:** Step 014a moved the dashboard's HTTP boundary from `http.server` to a small Flask application (`llm_metrics/web.py`, `create_app()` factory), keeping routes, query validation, page HTML, and statuses unchanged. `dashboard.py` became an HTTP-free application/view layer, and only `web.py` imports Flask. Flask is the first runtime dependency: pinned with sha256 hashes in `requirements.txt` and installed by `run.sh` through a standard-library installer that brings a hash-verified pip zipapp when the venv has none.

**Question:** Walk through a request to `/requests?data=real` after the refactor. Where does each responsibility live, and how did you keep validation identical?

## Answer

1. Flask dispatches `/requests` to `web._requests_page`.
2. The route reads the query with `flask.request.args.to_dict(flat=False)`. This gives `{name: [every value]}`, including blank values, the same shape `urllib.parse.parse_qs(..., keep_blank_values=True)` produced before.
3. It passes that to `dashboard.parse_requests_query`. The validation code (`_parse_choice`) did not change: an unknown, empty, or repeated value raises `ValueError`, and the route turns that into a 400 page that lists the valid values without echoing the bad one.
4. On success the route calls `dashboard.build_requests_page(db_path, "real")`, which calls `storage.load_recent_requests` and the unchanged renderer.
5. `web._html` wraps the page in a `flask.Response` (200, `text/html; charset=utf-8`), and an `after_request` hook adds the Content-Security-Policy.

The route contains no SQL and no HTML.

The tests were split by layer. Validation and rendering keep their existing unit tests, which call `dashboard` directly with parsed parameters. The HTTP behavior is tested through Flask's test client against a temporary database, with socket connections patched to fail. That covers every window × metric combination, the invalid queries (including `?window` with no value), 404s, 405s, and the header on error pages.

## Critique

- **Good:** It's a mechanical, low-risk move. The parameter shape is the one piece that could silently change validation, and it was chosen to match exactly. Routes stay a few lines each.
- **Weak:** The three route functions repeat a parse → 400 → build pattern. Error pages (404/405/500) use Flask's defaults, not the dashboard layout.
- **Improve:** If more routes arrive, factor the parse-or-400 step into one helper. Render error pages with the shared layout once templates exist (014b).
