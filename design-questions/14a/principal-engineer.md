# Step 14a — Principal engineer

**Step context:** Step 014a moved the dashboard's HTTP boundary from `http.server` to a small Flask application (`llm_metrics/web.py`, `create_app()` factory), keeping routes, query validation, page HTML, and statuses unchanged. `dashboard.py` became an HTTP-free application/view layer, and only `web.py` imports Flask. Flask is the first runtime dependency: pinned with sha256 hashes in `requirements.txt` and installed by `run.sh` through a standard-library installer that brings a hash-verified pip zipapp when the venv has none.

**Question:** How do you make sure Flask stays at the edge and doesn't become the center of the system, and why an application factory?

## Answer

The dependency direction is `web → dashboard → storage`, and it's enforced, not just documented. Two tests check it:

- An AST test reads every module in `llm_metrics/` except `web.py` and fails if any imports `flask` or `werkzeug`.
- A fresh-process test imports every benchmark, provider, pricing, storage, analytics, and CLI module and asserts neither package was loaded, which also catches imports pulled in indirectly.

So measurement and `real_smoke` run without Flask, and a future scheduler or API can reuse `dashboard`/`storage` without a web server.

`create_app(db_path=None)` exists so nothing happens at import time:

- There is no global app, database connection, or configuration read during import; a test checks that importing `web` prints nothing and creates no database.
- The database path is resolved when the app is created (`LLM_METRICS_DB_PATH` or the default) and opened per request, so each test builds an app on its own temporary database.
- Configuration stays one value in `app.config`, not a configuration framework.

## Critique

- **Good:** The boundary is small and checked by tests. Swapping the renderer (014b) or the server (later) touches one module each.
- **Weak:** `dashboard.py` still mixes page logic with rendering, so it's the next monolith risk. The AST rule is a denylist (`flask`, `werkzeug`); a future web dependency such as a templating add-on would need adding to it.
- **Improve:** In 014c, split view preparation (which population, which window, which data) from HTML rendering. Turn the import rule into an allowlist of what each layer may import.
