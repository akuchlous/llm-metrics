"""Local TTFT dashboard: one HTML page with a server-rendered SVG line chart.

Usage: python -m llm_metrics.dashboard   (serves http://127.0.0.1:8000/)

GET /?window=24h|7d|30d selects a time window ending at the current UTC time
(default 7d). Any other window value is rejected with HTTP 400.

Uses only the standard library. Binds to 127.0.0.1 so it is not reachable from
other machines. Shows only simulated test observations from the dummy provider.
"""

import math
import sys
from datetime import datetime, timedelta, timezone
from html import escape
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from llm_metrics.config import ConfigError, get_db_path, get_port
from llm_metrics.percentiles import percentile
from llm_metrics.providers import DummyProvider
from llm_metrics.storage import load_observations

HOST = "127.0.0.1"

# What the dashboard displays: simulated TTFT from the dummy provider only.
ENVIRONMENT = "test"
PROVIDER = DummyProvider.name
MODEL = DummyProvider.model
METRIC = "ttft"
PERCENTILES = (50, 95, 99)

# Selectable windows, each ending at the current UTC time. The default is 7d:
# with hourly data it holds ~168 observations, enough for nearest-rank p99 to
# differ from the maximum (24h would hold only ~24).
WINDOWS = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}
DEFAULT_WINDOW = "7d"

# Chart geometry in SVG units (the SVG scales to the page width).
WIDTH, HEIGHT = 800, 300
LEFT, RIGHT, TOP, BOTTOM = 60, 20, 20, 40

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>llm-metrics — TTFT</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; background: #fff; }}
  .label {{ display: inline-block; background: #b45309; color: #fff; font-weight: 700; padding: .3rem .7rem; border-radius: 4px; letter-spacing: .05em; }}
  .latest {{ font-size: 2rem; font-weight: 700; margin: .2rem 0; }}
  .muted {{ color: #555; }}
  .percentiles {{ font-size: 1.15rem; }}
  svg {{ width: 100%; height: auto; border: 1px solid #ddd; }}
  nav a {{ margin-right: .8rem; }}
  nav a[aria-current] {{ font-weight: 700; color: #1a1a1a; text-decoration: none; }}
</style>
</head>
<body>
<h1>llm-metrics</h1>
<p class="label">TEST / SIMULATED DATA</p>
<p>Provider: <b>{provider}</b> · Model: <b>{model}</b> · Metric: <b>TTFT</b></p>
<p class="muted">Simulated observations from the dummy provider. Not real LLM performance.</p>
{body}
</body>
</html>
"""


def _parse_time(recorded_at: str) -> datetime:
    return datetime.strptime(recorded_at, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)


def _display_time(recorded_at: str) -> str:
    return _parse_time(recorded_at).strftime("%Y-%m-%d %H:%M UTC")


def _chart_svg(observations: list[tuple[str, float]], start: datetime, end: datetime) -> str:
    """Line chart of value_ms over the whole window (x is proportional to time)."""
    t_min, t_max = start.timestamp(), end.timestamp()
    times = [_parse_time(t).timestamp() for t, _ in observations]
    values = [v for _, v in observations]
    # Headroom above the largest value, rounded up to a whole 100 ms (never 0).
    y_max = max(100, math.ceil(max(values) * 1.1 / 100) * 100)

    def x(t: float) -> float:
        return LEFT + (t - t_min) / (t_max - t_min) * (WIDTH - LEFT - RIGHT)

    def y(v: float) -> float:
        return HEIGHT - BOTTOM - v / y_max * (HEIGHT - TOP - BOTTOM)

    points = " ".join(f"{x(t):.1f},{y(v):.1f}" for t, v in zip(times, values))
    axis_bottom = HEIGHT - BOTTOM
    return f"""<svg viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-label="TTFT over time">
  <line x1="{LEFT}" y1="{TOP}" x2="{LEFT}" y2="{axis_bottom}" stroke="#999"/>
  <line x1="{LEFT}" y1="{axis_bottom}" x2="{WIDTH - RIGHT}" y2="{axis_bottom}" stroke="#999"/>
  <text x="{LEFT - 6}" y="{TOP + 4}" text-anchor="end" font-size="12">{y_max:.0f} ms</text>
  <text x="{LEFT - 6}" y="{axis_bottom}" text-anchor="end" font-size="12">0 ms</text>
  <text x="{LEFT}" y="{HEIGHT - 15}" font-size="12">{start:%Y-%m-%d %H:%M} UTC</text>
  <text x="{WIDTH - RIGHT}" y="{HEIGHT - 15}" text-anchor="end" font-size="12">{end:%Y-%m-%d %H:%M} UTC (now)</text>
  <polyline fill="none" stroke="#2563eb" stroke-width="1.5" points="{points}"/>
  <circle cx="{x(times[-1]):.1f}" cy="{y(values[-1]):.1f}" r="4" fill="#2563eb"/>
</svg>"""


def _window_nav(selected: str | None) -> str:
    links = []
    for name in WINDOWS:
        current = ' aria-current="page"' if name == selected else ""
        links.append(f'<a href="/?window={name}"{current}>{name}</a>')
    return '<nav aria-label="Time window">Window: ' + "".join(links) + "</nav>"


def parse_window(query: str) -> str:
    """Return the window named by a URL query string, or DEFAULT_WINDOW if absent.

    Raises ValueError for any other value, an empty value, or a repeated parameter.
    Other query parameters are ignored.
    """
    values = parse_qs(query, keep_blank_values=True).get("window")
    if values is None:
        return DEFAULT_WINDOW
    if len(values) != 1 or values[0] not in WINDOWS:
        raise ValueError("Unknown time window.")
    return values[0]


def window_bounds(window: str, now: datetime) -> tuple[datetime, datetime]:
    """(start, end) of a window ending at `now`. Both bounds are inclusive."""
    return now - WINDOWS[window], now


def render_page(
    observations: list[tuple[str, float]], window: str, start: datetime, end: datetime
) -> str:
    """Full HTML page for one window's (recorded_at, value_ms) observations, oldest first.

    Every derived value (count, latest, percentiles, chart) uses `observations`.
    """
    header = (
        _window_nav(window)
        + f'\n<p class="muted">Window {window}: {start:%Y-%m-%d %H:%M} UTC'
        f" to {end:%Y-%m-%d %H:%M} UTC (now), inclusive.</p>\n"
    )
    if not observations:
        body = (
            f"<p><b>No observations in the selected window ({window}).</b> Run "
            "<code>./run.sh</code> to record one, or choose a longer window.</p>"
        )
    else:
        latest_at, latest_value = observations[-1]
        values = [v for _, v in observations]
        summary = " · ".join(
            f"p{p} <b>{percentile(values, p):.1f} ms</b>" for p in PERCENTILES
        )
        body = (
            f'<p class="muted">Latest TTFT ({_display_time(latest_at)})</p>\n'
            f'<p class="latest">{latest_value:.1f} ms</p>\n'
            f'<p class="percentiles">TTFT {summary}'
            f' <span class="muted">(nearest-rank, n = {len(observations)})</span></p>\n'
            f'<p class="muted">{len(observations)} observations in window,'
            f" first {_display_time(observations[0][0])}, latest {_display_time(latest_at)}.</p>\n"
            + _chart_svg(observations, start, end)
        )
    return PAGE.format(provider=escape(PROVIDER), model=escape(MODEL), body=header + body)


def render_invalid_window_page() -> str:
    """Page for an unknown window value. The bad value is not echoed back."""
    body = (
        _window_nav(None)
        + "\n<p><b>Unknown time window.</b> Choose one of: "
        + ", ".join(WINDOWS)
        + f". The default is {DEFAULT_WINDOW}.</p>"
    )
    return PAGE.format(provider=escape(PROVIDER), model=escape(MODEL), body=body)


def build_page(db_path: Path, window: str, now: datetime) -> str:
    """Load the window's observations from SQLite and render the page."""
    start, end = window_bounds(window, now)
    observations = load_observations(
        db_path, ENVIRONMENT, PROVIDER, MODEL, METRIC, start=start, end=end
    )
    return render_page(observations, window, start, end)


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlsplit(self.path)
        if url.path != "/":
            self.send_error(404)
            return
        try:
            window = parse_window(url.query)
        except ValueError:
            self._send_html(400, render_invalid_window_page())
            return
        now = datetime.now(timezone.utc)
        self._send_html(200, build_page(self.server.db_path, window, now))

    def _send_html(self, status: int, page: str) -> None:
        body = page.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        # The page has no scripts and loads nothing external.
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def make_server(db_path: Path, port: int) -> HTTPServer:
    """Create (but do not start) the dashboard server on 127.0.0.1."""
    server = HTTPServer((HOST, port), _Handler)
    server.db_path = db_path
    return server


def main() -> int:
    try:
        port = get_port()
    except ConfigError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    try:
        server = make_server(get_db_path(), port)
    except OSError as e:  # most often: the port is already in use
        print(
            f"Error: cannot serve the dashboard on {HOST}:{port} ({e.strerror}). "
            "Is it already running? Set LLM_METRICS_PORT to use another port.",
            file=sys.stderr,
        )
        return 1
    bound_port = server.server_address[1]
    print(f"Dashboard: http://{HOST}:{bound_port}/  (Ctrl+C to stop)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
