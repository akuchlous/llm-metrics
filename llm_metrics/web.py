"""Flask application: the HTTP boundary of the local dashboard.

Usage: python -m llm_metrics.web   (serves http://127.0.0.1:8000/)

Owns route dispatch, query parameter access, template rendering, HTTP status
codes and headers, and serving on 127.0.0.1. What each page shows comes from
`dashboard` (query validation, data loading through `storage`, view data);
the markup lives in `llm_metrics/templates/` and the stylesheet in
`llm_metrics/static/`. This module contains no SQL and no HTML. Dependency
direction:

    web (Flask, Jinja templates) -> dashboard -> storage

This is the only module that imports Flask, Werkzeug, or Jinja. Measurement,
providers, pricing, storage, and analytics must keep working without them.

Routes (GET only; unknown paths are 404):

- `/?window=&metric=`: aggregate page.
- `/requests?data=simulated|real`: individual attempts.
- `/spend?window=`: Benchmark API Spend (real data only).

An invalid query value returns 400 with the list of valid values; the value
itself is never echoed.

Security: binds to 127.0.0.1 only, never runs in debug mode (no Werkzeug
debugger, no stack traces in responses), renders every value with Jinja
autoescaping (no `|safe` or `Markup` anywhere), and sends a
Content-Security-Policy on every response that allows no scripts, no inline
styles, and nothing external: only the stylesheet served from this app.
"""

import datetime
import pathlib
import socket
import sys

import flask
from werkzeug import serving

from llm_metrics import config
from llm_metrics import dashboard

HOST = "127.0.0.1"
# The pages have no scripts and load only /static/dashboard.css, so the policy
# blocks everything else, including inline styles and scripts.
CONTENT_SECURITY_POLICY = "default-src 'none'; style-src 'self'"
# Key in `app.config` holding the SQLite database path the pages read.
DB_PATH_KEY = "LLM_METRICS_DB_PATH"


def create_app(db_path: pathlib.Path | None = None) -> flask.Flask:
    """Creates the dashboard application. No database or network access.

    The database is opened per request, so creating an app (for example in a
    test) has no side effects.

    Args:
        db_path: SQLite database to read. Defaults to `config.get_db_path()`
            (`LLM_METRICS_DB_PATH` or `data/llm_metrics.db`), read now rather
            than at import time.

    Returns:
        A configured Flask application.
    """
    # Templates and the stylesheet are found next to this module, in
    # llm_metrics/templates/ and llm_metrics/static/ (served at /static/).
    app = flask.Flask(__name__)
    # Flask reads FLASK_DEBUG from the environment; debug mode must never be
    # enabled by accident because it can expose stack traces.
    app.debug = False
    # Drop the whitespace left by template tags, so the HTML stays readable.
    app.jinja_env.trim_blocks = True
    app.jinja_env.lstrip_blocks = True
    app.config[DB_PATH_KEY] = (
        config.get_db_path() if db_path is None else db_path
    )
    app.add_url_rule("/", "aggregate", _aggregate_page, methods=["GET"])
    app.add_url_rule("/requests", "requests", _requests_page, methods=["GET"])
    app.add_url_rule("/spend", "spend", _spend_page, methods=["GET"])
    app.after_request(_add_security_headers)
    return app


def _db_path() -> pathlib.Path:
    return flask.current_app.config[DB_PATH_KEY]


def _query_params() -> dashboard.QueryParams:
    # flat=False keeps every value of a repeated parameter (and blank values),
    # so the dashboard can reject them instead of silently picking one.
    return flask.request.args.to_dict(flat=False)


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def render_page(template: str, view: dict, status: int = 200) -> flask.Response:
    """Renders a page template with its view as an HTML response.

    Must run inside a request (or test request) context, because templates
    build the stylesheet URL with `url_for`.

    Args:
        template: Template file in llm_metrics/templates/, e.g. "spend.html".
        view: View data from a `dashboard.*_view` function; its keys become
            template variables.
        status: HTTP status code.
    """
    page = flask.render_template(template, **view)
    return flask.Response(page, status=status, mimetype="text/html")


def _invalid_query() -> flask.Response:
    return render_page(
        "invalid_query.html", dashboard.invalid_query_view(), status=400
    )


def _aggregate_page() -> flask.Response:
    try:
        window, metric = dashboard.parse_query(_query_params())
    except ValueError:
        return _invalid_query()
    view = dashboard.load_aggregate_view(_db_path(), window, metric, _now())
    return render_page("aggregate.html", view)


def _requests_page() -> flask.Response:
    try:
        data = dashboard.parse_requests_query(_query_params())
    except ValueError:
        return _invalid_query()
    view = dashboard.load_requests_view(_db_path(), data)
    return render_page("requests.html", view)


def _spend_page() -> flask.Response:
    try:
        window = dashboard.parse_spend_query(_query_params())
    except ValueError:
        return _invalid_query()
    view = dashboard.load_spend_view(_db_path(), window, _now())
    return render_page("spend.html", view)


def _add_security_headers(response: flask.Response) -> flask.Response:
    """Adds the Content-Security-Policy to every response, errors included."""
    response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
    return response


def make_server(
    app: flask.Flask, listening_socket: socket.socket
) -> serving.BaseWSGIServer:
    """Wraps an already-bound socket in Werkzeug's local development server.

    Binding is done by the caller so a busy port can be reported clearly;
    Werkzeug would otherwise print its own message and exit the process.

    Args:
        app: Application to serve.
        listening_socket: Socket bound to `HOST` and listening. The server
            uses a duplicate of it, so the caller may close the original.

    Returns:
        A single-threaded server; call `serve_forever()` to run it.
    """
    bound_host, bound_port = listening_socket.getsockname()[:2]
    return serving.make_server(
        bound_host, bound_port, app, fd=listening_socket.fileno()
    )


def main() -> int:
    """Serves the dashboard until interrupted.

    Returns:
        Process exit code: 0 after Ctrl+C, 1 if the port cannot be bound, 2
        for an invalid `LLM_METRICS_PORT`.
    """
    try:
        port = config.get_port()
    except config.ConfigError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    try:
        listening_socket = socket.create_server((HOST, port))
    except OSError as e:  # Most often: the port is already in use.
        print(
            f"Error: cannot serve the dashboard on {HOST}:{port}"
            f" ({e.strerror}). Is it already running? Set LLM_METRICS_PORT to"
            " use another port.",
            file=sys.stderr,
        )
        return 1
    with listening_socket:
        server = make_server(create_app(), listening_socket)
    # The real port matters when port 0 was requested; run.sh and tests read
    # it from this line.
    print(
        f"Dashboard: http://{HOST}:{server.port}/  (Ctrl+C to stop)",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
