# Step 014a — Implementation report

Prompt: `014a-flask-foundation.md`.

## Files changed

- **`llm_metrics/web.py` (new):** the Flask HTTP boundary.
  - `create_app(db_path=None)` application factory.
  - Routes `/`, `/requests`, `/spend` (GET only).
  - Query parameter access, status codes, and the Content-Security-Policy header on every response.
  - `make_server()` and `main()` serve on 127.0.0.1.
  - It is the only module that imports Flask or Werkzeug.
- **`llm_metrics/dashboard.py`:** now the HTTP-free application/view layer.
  - Removed the `http.server` handler, `make_server`, `main`, and `HOST`.
  - The parse functions take parsed parameters (`{name: [all values]}`) instead of a raw query string.
  - Added `build_requests_page()`, so routes never call storage directly.
  - Rendering is unchanged.
- **`requirements.txt` (new):** Flask and its six dependencies, pinned with sha256 hashes.
- **`scripts/install_requirements.py` (new):** hash-checked installer that works with the pip-less venv.
- **`run.sh`:** installs (or confirms) dependencies before the tests, and serves with `python -m llm_metrics.web`.
- **Tests:**
  - New `tests/test_web.py` (22 tests) and `tests/test_install_requirements.py` (9 tests).
  - `test_dashboard.py`: parse tests use parsed parameters; the socket-based server tests moved to `test_web.py`.
  - `test_run_script.py`: copies the provisioned venv, `requirements.txt`, and `scripts/` into its temporary repository.
  - `test_openai_provider.py`: the offline-import test also imports `llm_metrics.web`.
- **Docs:**
  - `DECISIONS.md`: D001, D012, D025, D026 and D029 revised; D056 and D057 added.
  - `PROJECT_STATUS.md`, `README.md`, `llm_metrics/README.md`, the style-check commands in `CODING_GUIDELINES.md`, and the progress line in the direction log.
  - `design-questions/14a/` and its index row.

## Dependency / bootstrap changes

- **First runtime dependency:** Flask 3.1.3. D001 (standard library first) now has its first earned exception. Measurement, providers, pricing, storage and analytics remain standard-library only.
- **`requirements.txt`:**
  - Pins every package exactly: Flask 3.1.3, Werkzeug 3.1.9, Jinja2 3.1.6, itsdangerous 2.2.0, click 8.5.0, blinker 1.9.0, MarkupSafe 3.0.4.
  - Lists the sha256 of every published file (163 hashes; MarkupSafe has per-platform wheels and no pure-Python wheel).
  - Every version was at least two weeks old when chosen. Nothing else was added: no Gunicorn, SQLAlchemy or frontend packages.
- **Install flags:** `pip install --require-hashes --only-binary=:all: --isolated`. Only those exact wheels can be installed, nothing is built from source, and user or global pip configuration is ignored.
- **The venv has no pip** (`venv --without-pip`, kept because `python3-venv`/`ensurepip` is missing on some Chromebooks, including this machine). The installer then downloads pip's official zipapp at a pinned version (26.2.1), verifies its sha256 before running it, and discards it. No sudo or system package is needed.
- **No network on normal runs:** a stamp file in the venv records the sha256 of the installed requirements. The network is needed only on the first run and after `requirements.txt` changes.
- **Verified for real:**
  - A fresh copy of the repository without `.venv` ran `./run.sh` end to end: venv created, pip zipapp verified, the 7 packages installed, all tests passed, and the dashboard served `GET / → 200`.
  - The existing venv then reported "Dependencies ready" with no download.

## Old vs new request path

| | Before | After |
|---|---|---|
| Server | `http.server.HTTPServer` + `BaseHTTPRequestHandler` in `dashboard.py` | Werkzeug's local server around a Flask app (`web.py`) on a socket that `web.main()` binds itself |
| Routing | `do_GET` comparing `url.path` strings | `app.add_url_rule` for `/`, `/requests`, `/spend` |
| Query access | `urllib.parse.parse_qs(query, keep_blank_values=True)` inside `dashboard` | `flask.request.args.to_dict(flat=False)` in `web`, passed to `dashboard.parse_*` |
| Validation | `dashboard._parse_choice` | unchanged: still rejects unknown, empty, and repeated values without echoing them |
| Data + HTML | `dashboard.build_page`, `build_spend_page`, and `storage.load_recent_requests` called from the handler | `dashboard.build_page`, `build_requests_page`, `build_spend_page`; routes never touch storage or SQL |
| Status/headers | `send_response`, manual CSP, `send_error(404)` | `flask.Response`; an `after_request` hook adds CSP to every response, errors included |
| Command | `python -m llm_metrics.dashboard` | `python -m llm_metrics.web` (`run.sh` updated) |

Request flow now: `GET /requests?data=real` → `web._requests_page` → `dashboard.parse_requests_query` → `dashboard.build_requests_page` → `storage.load_recent_requests` → `dashboard.render_requests_page` → `web._html` (200, `text/html; charset=utf-8`, CSP).

**Behavior preserved:**
- Same routes, query semantics, page HTML, and 200/400/404 statuses. The 400 page lists the valid values and never echoes the bad one.
- Same 127.0.0.1-only binding, same `LLM_METRICS_PORT` (0 = free port) with the printed `Dashboard: http://…` line, and the same "already running" message when the port is busy.

**Small, deliberate differences:**
- Non-GET methods return 405 (was 501); HEAD is answered for GET routes.
- 404/405/500 pages also carry the CSP header.
- An unhandled error returns Flask's generic 500 page and is logged server-side; no stack trace is sent.

## Safety

- **Debug mode is forced off** in `create_app` even if `FLASK_DEBUG=1`; the Werkzeug debugger is never attached (no `app.run`/`run_simple`).
- **No import-time side effects:** importing `web` creates no app, database or server. The database path is read when the app is created, and the database is opened per request.
- **Simulated vs real separation, labels, escaping, and the paid-call boundary are unchanged.** The web layer makes no provider calls, and `real_smoke` is untouched.

## Tests

217 tests, OK under the project venv on Python 3.13 (Python 3.11 is not installed here); none skipped.

**`test_web.py`:**
- **Aggregate route:** defaults and database data; every window × metric combination; unrelated parameters ignored; 7 invalid queries return 400 with the CSP, the bad value not echoed.
- **Requests route:** simulated by default, `data=real`, and invalid data values (400).
- **Spend route:** default 30d, real data only, every valid window, invalid windows (400).
- **Routing:** unknown paths return 404 with the CSP; POST returns 405.
- **No network:** socket connect and `urlopen` are patched to fail in every route test.
- **App factory:** uses an isolated temporary database, created only on the first request; the default path comes from `LLM_METRICS_DB_PATH` when the app is created; debug stays off with `FLASK_DEBUG=1`; a 500 response hides the error text, which is logged server-side.
- **Import and dependencies:**
  - Importing `web` and `dashboard` in a fresh process prints nothing and creates no database.
  - An AST check confirms no module other than `web.py` imports Flask or Werkzeug.
  - A fresh process importing every benchmark/data module loads neither.
- **Real server process on 127.0.0.1:** serves `/` with the CSP; a busy port gives exit 1 and the clear message with no traceback; an invalid port gives exit 2.

**`test_install_requirements.py`** (pip and downloads mocked):
- An up-to-date environment does nothing, and changed requirements trigger a reinstall.
- An existing pip is used with `--require-hashes --only-binary=:all: --isolated`.
- Without pip, the pinned zipapp is downloaded, verified, and run.
- A tampered zipapp is never run.
- A download failure and a failed install both leave no stamp.
- `requirements.txt` pins exactly Flask and its 6 dependencies, every one with sha256 hashes.

**Unchanged:** all existing measurement, storage, migration, cache, reliability, cost, workload, origin, provider, and offline tests.

**`./run.sh`** (APP_ENV unset, no `OPENAI_API_KEY`):
- "Dependencies ready", tests passed, history present, one simulated attempt saved (4 observations).
- Dashboard served by Flask: `GET / → 200`.
- The end-to-end `run.sh` test also passes, using a copy of the provisioned venv, so no download is needed.

**Style:** pyink, isort (google) and Google pylint report no findings for `llm_metrics`, `tests`, and `scripts`.

**No paid API call** was made.

## What deliberately remains mixed until 014b

- `dashboard.py` still builds HTML in Python: the `PAGE` layout string with inline CSS, the f-string renderers, and the inline SVG chart. It also still holds both page logic (validation, which data and window to load) and rendering.
- 014b replaces the renderers with Jinja templates. The routes in `web.py` already call only `dashboard.parse_*` and `dashboard.build_*`, so that change stays behind `dashboard` without touching routes, analytics, or storage.
- Separating view preparation from analytics/query orchestration is planned for 014c.

## Known limitations

- **Development server only:** Werkzeug's single-threaded server is fine for local use. Production serving is out of scope until deployment.
- **First run needs PyPI access**, as does every `requirements.txt` change. There is no offline wheel cache, and the pip zipapp also needs `bootstrap.pypa.io`.
- **Tests must run under the project venv** (`.venv/bin/python -m unittest`), because the web tests import Flask. The `run.sh` end-to-end test is skipped outside a venv.
- **Updating a dependency** means updating its version and all of its hashes together. There is no lock-file tool; hashes come from PyPI's JSON API.
- **Error pages:** 404/405/500 use Flask's default HTML pages, not the dashboard layout.
- **Unchanged from before:** user-facing text on the requests page still mentions "Step 010"; that is product copy, left for the template step.

## Design Q&A

**Why bind the socket in `web.main()` instead of letting Werkzeug do it?** Werkzeug's server prints its own message and calls `sys.exit(1)` when the port is busy, which would have replaced the existing, tested "Is it already running?" message. Binding with `socket.create_server((HOST, port))` and handing the socket to Werkzeug (`fd=`) keeps that message and keeps the 127.0.0.1-only bind in our code.

**Why hash-pin a framework for a local dashboard?** Flask is the first code from outside the standard library, and `run.sh` installs it automatically on every developer machine. With `--require-hashes` and `--only-binary=:all:`, a changed or substituted package fails the install instead of running. The same applies to the pip zipapp, which is verified before it executes.
