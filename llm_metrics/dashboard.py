"""Local TTFT dashboard: one HTML page with a server-rendered SVG line chart.

Usage: python -m llm_metrics.dashboard   (serves http://127.0.0.1:8000/)

Uses only the standard library. Binds to 127.0.0.1 so it is not reachable from
other machines. Shows only simulated test observations from the dummy provider.
"""

import math
import sys
from datetime import datetime, timezone
from html import escape
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from llm_metrics.config import ConfigError, get_db_path, get_port
from llm_metrics.providers import DummyProvider
from llm_metrics.storage import load_observations

HOST = "127.0.0.1"

# What the dashboard displays: simulated TTFT from the dummy provider only.
ENVIRONMENT = "test"
PROVIDER = DummyProvider.name
MODEL = DummyProvider.model
METRIC = "ttft"

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
  svg {{ width: 100%; height: auto; border: 1px solid #ddd; }}
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


def _chart_svg(observations: list[tuple[str, float]]) -> str:
    """Line chart of value_ms against time (x is proportional to real time)."""
    times = [_parse_time(t).timestamp() for t, _ in observations]
    values = [v for _, v in observations]
    t_min, t_max = min(times), max(times)
    # Headroom above the largest value, rounded up to a whole 100 ms (never 0).
    y_max = max(100, math.ceil(max(values) * 1.1 / 100) * 100)

    def x(t: float) -> float:
        if t_max == t_min:
            return (LEFT + WIDTH - RIGHT) / 2
        return LEFT + (t - t_min) / (t_max - t_min) * (WIDTH - LEFT - RIGHT)

    def y(v: float) -> float:
        return HEIGHT - BOTTOM - v / y_max * (HEIGHT - TOP - BOTTOM)

    points = " ".join(f"{x(t):.1f},{y(v):.1f}" for t, v in zip(times, values))
    first_label = _display_time(observations[0][0])
    last_label = _display_time(observations[-1][0])
    axis_bottom = HEIGHT - BOTTOM
    return f"""<svg viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-label="TTFT over time">
  <line x1="{LEFT}" y1="{TOP}" x2="{LEFT}" y2="{axis_bottom}" stroke="#999"/>
  <line x1="{LEFT}" y1="{axis_bottom}" x2="{WIDTH - RIGHT}" y2="{axis_bottom}" stroke="#999"/>
  <text x="{LEFT - 6}" y="{TOP + 4}" text-anchor="end" font-size="12">{y_max:.0f} ms</text>
  <text x="{LEFT - 6}" y="{axis_bottom}" text-anchor="end" font-size="12">0 ms</text>
  <text x="{LEFT}" y="{HEIGHT - 15}" font-size="12">{first_label}</text>
  <text x="{WIDTH - RIGHT}" y="{HEIGHT - 15}" text-anchor="end" font-size="12">{last_label}</text>
  <polyline fill="none" stroke="#2563eb" stroke-width="1.5" points="{points}"/>
  <circle cx="{x(times[-1]):.1f}" cy="{y(values[-1]):.1f}" r="4" fill="#2563eb"/>
</svg>"""


def render_page(observations: list[tuple[str, float]]) -> str:
    """Full HTML page for (recorded_at, value_ms) observations, oldest first."""
    if not observations:
        body = (
            "<p><b>No observations yet.</b> Run <code>./run.sh</code> to record one, or "
            "<code>python3 -m llm_metrics.seed_history</code> to add simulated history.</p>"
        )
    else:
        latest_at, latest_value = observations[-1]
        first_at = observations[0][0]
        body = (
            f'<p class="muted">Latest TTFT ({_display_time(latest_at)})</p>\n'
            f'<p class="latest">{latest_value:.1f} ms</p>\n'
            f'<p class="muted">All {len(observations)} observations,'
            f" {_display_time(first_at)} to {_display_time(latest_at)}.</p>\n"
            + _chart_svg(observations)
        )
    return PAGE.format(provider=escape(PROVIDER), model=escape(MODEL), body=body)


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/":
            self.send_error(404)
            return
        observations = load_observations(
            self.server.db_path, ENVIRONMENT, PROVIDER, MODEL, METRIC
        )
        body = render_page(observations).encode("utf-8")
        self.send_response(200)
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
