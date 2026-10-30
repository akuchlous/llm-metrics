"""Local metrics dashboard: server-rendered HTML pages, no JavaScript.

Usage: python -m llm_metrics.dashboard   (serves http://127.0.0.1:8000/)

GET /?window=24h|7d|30d&metric=total_latency|ttft|output_tokens_per_s|output_chunks_per_s
shows, for a time window ending at the current UTC time (default 7d), the observed
benchmark success rate of all attempts and one metric (default ttft) over
successful attempts as percentiles and a line chart. Any other, empty, or
repeated value is rejected with HTTP 400.

GET /requests?data=simulated|real lists the most recent individual benchmark
attempts (default simulated) with their outcome, token counts, latency,
throughput, and cost.

GET /spend?window=24h|7d|30d shows Benchmark API Spend: the known API token
cost of llm-metrics' own real benchmark requests, per provider and model
(default window 30d).

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
from llm_metrics.latency import METRICS
from llm_metrics.percentiles import percentile
from llm_metrics.providers import DummyProvider
from llm_metrics.outcomes import FAILURE_CATEGORIES, SUCCESS, success_rate
from llm_metrics.storage import (
    count_outcomes,
    load_observations,
    load_recent_requests,
    spend_by_model,
)

HOST = "127.0.0.1"

# What the dashboard displays: simulated observations from the dummy provider only.
ENVIRONMENT = "test"
PROVIDER = DummyProvider.name
MODEL = DummyProvider.model
PERCENTILES = (50, 95, 99)

# Selectable metrics are all of METRICS (name -> (label, unit)).
DEFAULT_METRIC = "ttft"

# Selectable windows, each ending at the current UTC time. The default is 7d:
# with hourly data it holds ~168 observations, enough for nearest-rank p99 to
# differ from the maximum (24h would hold only ~24).
WINDOWS = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}
DEFAULT_WINDOW = "7d"

RECENT_REQUESTS = 20  # rows on the /requests page

# Data populations: query value -> stored environment. Simulated (dummy) and
# real provider data are never shown on the same page.
DATA = {"simulated": "test", "real": "prod"}
DEFAULT_DATA = "simulated"

# Spend accumulates slowly, so its default window is the longest one.
SPEND_DEFAULT_WINDOW = "30d"

# Chart geometry in SVG units (the SVG scales to the page width).
WIDTH, HEIGHT = 800, 300
LEFT, RIGHT, TOP, BOTTOM = 60, 20, 20, 40

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>llm-metrics</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; background: #fff; }}
  .label {{ display: inline-block; background: #b45309; color: #fff; font-weight: 700; padding: .3rem .7rem; border-radius: 4px; letter-spacing: .05em; }}
  .latest {{ font-size: 2rem; font-weight: 700; margin: .2rem 0; }}
  .muted {{ color: #555; }}
  .percentiles {{ font-size: 1.15rem; }}
  svg {{ width: 100%; height: auto; border: 1px solid #ddd; }}
  nav a {{ margin-right: .8rem; }}
  nav a[aria-current] {{ font-weight: 700; color: #1a1a1a; text-decoration: none; }}
  .views {{ margin-bottom: 1rem; }}
  .table-wrap {{ overflow-x: auto; }}
  table {{ border-collapse: collapse; font-size: .85rem; }}
  th, td {{ padding: .3rem .45rem; border-bottom: 1px solid #ddd; text-align: right; white-space: nowrap; }}
  th {{ white-space: normal; vertical-align: bottom; }}
  th:first-child, td:first-child, th:nth-child(2), td:nth-child(2), th:nth-child(3), td:nth-child(3),
  th:last-child, td:last-child {{ text-align: left; }}
  .primary {{ font-weight: 700; }}
  .failed {{ color: #b91c1c; font-weight: 700; }}
  .reliability {{ border: 1px solid #ddd; padding: .2rem 1rem .6rem; margin: 1rem 0; }}
  .label.real {{ background: #1d4ed8; }}
  tr.total td {{ font-weight: 700; border-top: 2px solid #999; }}
</style>
</head>
<body>
<h1>llm-metrics</h1>
{views}
{data_header}
{body}
</body>
</html>
"""


VIEWS = {"/": "Aggregate", "/requests": "Recent requests", "/spend": "Benchmark API Spend"}

SIMULATED_HEADER = (
    '<p class="label">TEST / SIMULATED DATA</p>\n'
    f"<p>Provider: <b>{escape(PROVIDER)}</b> · Model: <b>{escape(MODEL)}</b></p>\n"
    '<p class="muted">Simulated observations from the dummy provider. Not real LLM performance.</p>'
)
REAL_HEADER = (
    '<p class="label real">REAL PROVIDER DATA</p>\n'
    '<p class="muted">Real API calls made by llm-metrics\' own benchmark runner. Never mixed'
    " with simulated data.</p>"
)


def _page(body: str, view: str | None, real: bool = False) -> str:
    """Wrap a page body in the shared layout. `view` is the current path, if any;
    `real` selects the real-provider data label instead of the simulated one."""
    links = []
    for path, name in VIEWS.items():
        current = ' aria-current="page"' if path == view else ""
        links.append(f'<a href="{path}"{current}>{name}</a>')
    views = f'<nav class="views" aria-label="View">{"".join(links)}</nav>'
    data_header = REAL_HEADER if real else SIMULATED_HEADER
    return PAGE.format(views=views, data_header=data_header, body=body)


def _parse_time(recorded_at: str) -> datetime:
    return datetime.strptime(recorded_at, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)


def _display_time(recorded_at: str) -> str:
    return _parse_time(recorded_at).strftime("%Y-%m-%d %H:%M UTC")


def _chart_svg(
    observations: list[tuple[str, float]], label: str, unit: str, start: datetime, end: datetime
) -> str:
    """Line chart of values over the whole window (x is proportional to time)."""
    t_min, t_max = start.timestamp(), end.timestamp()
    times = [_parse_time(t).timestamp() for t, _ in observations]
    values = [v for _, v in observations]
    # Headroom above the largest value, rounded up to a whole 100 units (never 0).
    y_max = max(100, math.ceil(max(values) * 1.1 / 100) * 100)

    def x(t: float) -> float:
        return LEFT + (t - t_min) / (t_max - t_min) * (WIDTH - LEFT - RIGHT)

    def y(v: float) -> float:
        return HEIGHT - BOTTOM - v / y_max * (HEIGHT - TOP - BOTTOM)

    points = " ".join(f"{x(t):.1f},{y(v):.1f}" for t, v in zip(times, values))
    axis_bottom = HEIGHT - BOTTOM
    return f"""<svg viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-label="{label} over time">
  <line x1="{LEFT}" y1="{TOP}" x2="{LEFT}" y2="{axis_bottom}" stroke="#999"/>
  <line x1="{LEFT}" y1="{axis_bottom}" x2="{WIDTH - RIGHT}" y2="{axis_bottom}" stroke="#999"/>
  <text x="{LEFT - 6}" y="{TOP + 4}" text-anchor="end" font-size="12">{y_max:.0f}</text>
  <text x="{LEFT - 6}" y="{axis_bottom}" text-anchor="end" font-size="12">0</text>
  <text x="{LEFT + 6}" y="{TOP + 4}" font-size="12" fill="#555">{unit}</text>
  <text x="{LEFT}" y="{HEIGHT - 15}" font-size="12">{start:%Y-%m-%d %H:%M} UTC</text>
  <text x="{WIDTH - RIGHT}" y="{HEIGHT - 15}" text-anchor="end" font-size="12">{end:%Y-%m-%d %H:%M} UTC (now)</text>
  <polyline fill="none" stroke="#2563eb" stroke-width="1.5" points="{points}"/>
  <circle cx="{x(times[-1]):.1f}" cy="{y(values[-1]):.1f}" r="4" fill="#2563eb"/>
</svg>"""


def _nav(window: str | None, metric: str | None) -> str:
    """Window and metric links. Each link keeps the other current selection."""
    keep_metric = metric or DEFAULT_METRIC
    keep_window = window or DEFAULT_WINDOW

    def link(href_window: str, href_metric: str, text: str, current: bool) -> str:
        aria = ' aria-current="page"' if current else ""
        return f'<a href="/?window={href_window}&amp;metric={href_metric}"{aria}>{text}</a>'

    windows = "".join(link(w, keep_metric, w, w == window) for w in WINDOWS)
    metrics = "".join(
        link(keep_window, m, label, m == metric) for m, (label, _unit) in METRICS.items()
    )
    return (
        f'<nav aria-label="Metric">Metric: {metrics}</nav>\n'
        f'<nav aria-label="Time window">Window: {windows}</nav>'
    )


def _parse_choice(params: dict[str, list[str]], name: str, choices, default: str) -> str:
    values = params.get(name)
    if values is None:
        return default
    if len(values) != 1 or values[0] not in choices:
        raise ValueError(f"Invalid {name}.")
    return values[0]


def parse_query(query: str) -> tuple[str, str]:
    """Return (window, metric) from a URL query string, using defaults when absent.

    Raises ValueError for an unknown, empty, or repeated window or metric.
    Other query parameters are ignored.
    """
    params = parse_qs(query, keep_blank_values=True)
    window = _parse_choice(params, "window", WINDOWS, DEFAULT_WINDOW)
    metric = _parse_choice(params, "metric", METRICS, DEFAULT_METRIC)
    return window, metric


def window_bounds(window: str, now: datetime) -> tuple[datetime, datetime]:
    """(start, end) of a window ending at `now`. Both bounds are inclusive."""
    return now - WINDOWS[window], now


def _reliability_section(outcome_counts: dict[str, int], window: str) -> str:
    """Observed benchmark success rate for all attempts in the window."""
    title = f"<h2>Observed benchmark success rate ({window})</h2>\n"
    scope = (
        '<p class="muted">All benchmark attempts made by this runner in the window,'
        " successful or not. This is what our runner observed, not the provider's"
        " overall uptime.</p>\n"
    )
    rate = success_rate(outcome_counts)
    if rate is None:
        body = f"<p><b>No benchmark attempts in the selected window ({window})</b>, so no success rate.</p>"
    else:
        failures = "".join(
            f"<tr><td>{label}</td><td>{rate['failures_by_category'][category]}</td></tr>"
            for category, label in FAILURE_CATEGORIES.items()
        )
        body = (
            f'<p class="latest">{rate["success_rate"] * 100:.1f}%</p>\n'
            f"<p>{rate['successes']} of {rate['attempts']} attempts succeeded"
            f" ({rate['failures']} failed, {rate['failure_rate'] * 100:.1f}%).</p>\n"
            f"<table><tr><th>Failure category</th><th>Attempts</th></tr>{failures}</table>"
        )
    return f'<section class="reliability">{title}{scope}{body}</section>\n'


def render_page(
    observations: list[tuple[str, float]],
    window: str,
    metric: str,
    start: datetime,
    end: datetime,
    outcome_counts: dict[str, int],
) -> str:
    """Full HTML page for one window: success rate over all attempts
    (`outcome_counts`), then one metric's (recorded_at, value) rows, oldest first.

    Every derived metric value (count, latest, percentiles, chart) uses
    `observations`, which contain successful measurements only.
    """
    label, unit = METRICS[metric]
    header = (
        _nav(window, metric)
        + f'\n<p class="muted">Window {window}: {start:%Y-%m-%d %H:%M} UTC'
        f" to {end:%Y-%m-%d %H:%M} UTC (now), inclusive.</p>\n"
        + _reliability_section(outcome_counts, window)
        + f"<h2>{label} (successful attempts only)</h2>\n"
    )
    if not observations:
        body = (
            f"<p><b>No {label} observations in the selected window ({window}).</b> Run "
            "<code>./run.sh</code> to record one, or choose a longer window.</p>"
        )
    else:
        latest_at, latest_value = observations[-1]
        values = [v for _, v in observations]
        summary = " · ".join(
            f"p{p} <b>{percentile(values, p):.1f} {unit}</b>" for p in PERCENTILES
        )
        body = (
            f'<p class="muted">Latest {label} ({_display_time(latest_at)})</p>\n'
            f'<p class="latest">{latest_value:.1f} {unit}</p>\n'
            f'<p class="percentiles">{label} {summary}'
            f' <span class="muted">(nearest-rank, n = {len(observations)})</span></p>\n'
            f'<p class="muted">{len(observations)} observation{"" if len(observations) == 1 else "s"} in window,'
            f" first {_display_time(observations[0][0])}, latest {_display_time(latest_at)}.</p>\n"
            + _chart_svg(observations, label, unit, start, end)
        )
    return _page(header + body, "/")


def render_invalid_query_page() -> str:
    """Page for an invalid query value. The bad value is not echoed back."""
    body = (
        _nav(None, None)
        + "\n<p><b>Invalid window or metric</b> (or data) value. Windows: "
        + ", ".join(WINDOWS)
        + f" (default {DEFAULT_WINDOW}; {SPEND_DEFAULT_WINDOW} on Benchmark API Spend). Metrics: "
        + ", ".join(METRICS)
        + f" (default {DEFAULT_METRIC}). Data on Recent requests: "
        + ", ".join(DATA)
        + f" (default {DEFAULT_DATA}).</p>"
    )
    return _page(body, None)


def build_page(db_path: Path, window: str, metric: str, now: datetime) -> str:
    """Load one metric's observations for the window from SQLite and render the page."""
    start, end = window_bounds(window, now)
    observations = load_observations(
        db_path, ENVIRONMENT, PROVIDER, MODEL, metric, start=start, end=end
    )
    counts = count_outcomes(db_path, ENVIRONMENT, PROVIDER, MODEL, start=start, end=end)
    return render_page(observations, window, metric, start, end, counts)


def _number(value: float | None, spec: str) -> str:
    return "—" if value is None else format(value, spec)


def _data_nav(selected: str | None) -> str:
    links = []
    for name in DATA:
        current = ' aria-current="page"' if name == selected else ""
        links.append(f'<a href="/requests?data={name}"{current}>{name}</a>')
    return f'<nav aria-label="Data">Data: {"".join(links)}</nav>\n'


def parse_requests_query(query: str) -> str:
    """Return the data population ("simulated" or "real") from a /requests query
    string. Raises ValueError for an unknown, empty, or repeated value."""
    return _parse_choice(parse_qs(query, keep_blank_values=True), "data", DATA, DEFAULT_DATA)


def _text(value: str | None) -> str:
    """Escaped stored text, or "—" when unknown (NULL)."""
    return "—" if value is None else escape(value)


def _origin(cloud: str | None, region: str | None) -> str:
    if cloud is None and region is None:
        return "—"
    return f"{_text(cloud)} / {_text(region)}"


def render_requests_page(requests: list[dict], data: str = DEFAULT_DATA) -> str:
    """Table of individual requests (newest first) of one data population."""
    real = data == "real"
    if real:
        accounting = (
            " Token counts are reported by the provider; costs use the rates stored with"
            " each request (USD)."
        )
        empty = ("No real benchmark attempts yet. Run <code>python -m llm_metrics.real_smoke</code>"
                 " (one paid request).")
    else:
        accounting = (
            " Token counts use a <b>simulated</b> tokenizer and costs use <b>simulated</b>"
            " prices (USD); they do not match any real provider."
        )
        empty = ("No benchmark attempts yet. Run <code>./run.sh</code> to record one."
                 " (Observations recorded before Step 010 have no request details.)")
    intro = (
        f"<h2>Recent requests</h2>\n{_data_nav(data)}<p class=\"muted\">The {RECENT_REQUESTS}"
        f" most recent benchmark attempts, successful or failed.{accounting} Total"
        " latency is a successful request's response time; TTFT is shown for streaming"
        " diagnostics. Token throughput is the provider's output token count divided by"
        " the time from the first to the last output chunk (TTFT excluded); chunk"
        " throughput counts stream chunks, not tokens. <i>Workload</i> is the benchmark"
        " case that was run; <i>Origin</i> is where the benchmark runner executed"
        " (cloud / region), not where the provider served it. For failed attempts,"
        " tokens, cost, and performance are unknown (—); <i>Failed after</i> is the time"
        " until the failure was detected.</p>\n"
    )
    if not requests:
        return _page(intro + f"<p><b>{empty}</b></p>", "/requests", real)
    # Most important first (time, latency, tokens, total cost); the table scrolls
    # sideways on narrow screens.
    header = (
        "<tr><th>Time (UTC)</th><th>Request</th><th>Outcome</th>"
        "<th>Total latency (ms)</th><th>TTFT (ms)</th><th>Throughput (tokens/s)</th>"
        "<th>Throughput (chunks/s)</th>"
        "<th>Input tokens</th><th>Output tokens</th><th>Max output tokens</th>"
        "<th>Total cost ($)</th><th>Input cost ($)</th><th>Output cost ($)</th>"
        "<th>Failed after (ms)</th><th>Provider / model</th><th>Workload</th>"
        "<th>Origin</th></tr>"
    )
    rows = []
    for r in requests:
        metrics = r["metrics"]
        if r["outcome"] == SUCCESS:
            outcome = "success"
        else:
            failure_label = escape(FAILURE_CATEGORIES.get(r["outcome"], r["outcome"]))
            outcome = f'<span class="failed">FAILED</span>: {failure_label}'
        rows.append(
            "<tr>"
            f"<td>{_display_time(r['recorded_at'])}</td>"
            f"<td><code title=\"{escape(r['id'])}\">{escape(r['id'][:8])}</code></td>"
            f"<td>{outcome}</td>"
            f"<td class=\"primary\">{_number(metrics.get('total_latency'), '.1f')}</td>"
            f"<td>{_number(metrics.get('ttft'), '.1f')}</td>"
            f"<td>{_number(metrics.get('output_tokens_per_s'), '.1f')}</td>"
            f"<td>{_number(metrics.get('output_chunks_per_s'), '.1f')}</td>"
            f"<td>{_number(r['input_tokens'], 'd')}</td>"
            f"<td>{_number(r['output_tokens'], 'd')}</td>"
            f"<td>{r['requested_max_output_tokens']:d}</td>"
            f"<td class=\"primary\">{_number(r['total_cost'], '.6f')}</td>"
            f"<td>{_number(r['input_cost'], '.6f')}</td>"
            f"<td>{_number(r['output_cost'], '.6f')}</td>"
            f"<td>{_number(r['failed_after_ms'], '.1f')}</td>"
            f"<td>{escape(r['provider'])} / {escape(r['model'])}</td>"
            f"<td>{_text(r['workload_id'])}</td>"
            f"<td>{_origin(r['origin_cloud'], r['origin_region'])}</td>"
            "</tr>"
        )
    table = f'<div class="table-wrap"><table>{header}{"".join(rows)}</table></div>'
    return _page(intro + table, "/requests", real)


def parse_spend_query(query: str) -> str:
    """Return the window for /spend (default SPEND_DEFAULT_WINDOW). Raises
    ValueError for an unknown, empty, or repeated value."""
    return _parse_choice(parse_qs(query, keep_blank_values=True), "window", WINDOWS,
                         SPEND_DEFAULT_WINDOW)


def _money(value: float | None) -> str:
    return "unknown" if value is None else f"${value:.6f}"


def render_spend_page(rows: list[dict], window: str, start: datetime, end: datetime) -> str:
    """Benchmark API Spend for one window, from spend_by_model rows (real data only)."""
    links = []
    for name in WINDOWS:
        current = ' aria-current="page"' if name == window else ""
        links.append(f'<a href="/spend?window={name}"{current}>{name}</a>')
    intro = (
        "<h2>Benchmark API Spend</h2>\n"
        f'<nav aria-label="Time window">Window: {"".join(links)}</nav>\n'
        f'<p class="muted">Window {window}: {start:%Y-%m-%d %H:%M} UTC to'
        f" {end:%Y-%m-%d %H:%M} UTC (now), inclusive.</p>\n"
        "<p>This is <b>the API token cost incurred by llm-metrics to run its own benchmark"
        " requests</b>, from the token counts each provider reported and the rates stored"
        " with each request (USD). It is <b>not</b> the provider's revenue, not what every"
        " user pays, not hosting or infrastructure cost, and not a workload-independent"
        " price comparison. Only real provider requests are included; simulated data never"
        " is.</p>\n"
        '<p class="muted">Spend counts successful calls only. A failed attempt\'s cost is'
        " unknown (a provider may still have billed part of it), so it is counted under"
        " <i>Failed attempts</i>, never added as $0.</p>\n"
    )
    if not rows:
        return _page(
            intro + f"<p><b>No real benchmark attempts in the selected window ({window}).</b></p>",
            "/spend", real=True,
        )
    header = (
        "<tr><th>Provider</th><th>Model</th><th>Successful paid calls</th>"
        "<th>Input tokens</th><th>Output tokens</th><th>Total cost</th>"
        "<th>Failed attempts (cost unknown)</th></tr>"
    )
    body = []
    for r in rows:
        body.append(
            "<tr>"
            f"<td>{escape(r['provider'])}</td><td>{escape(r['model'])}</td>"
            f"<td>{r['successful_calls']}</td>"
            f"<td>{_number(r['input_tokens'], 'd')}</td>"
            f"<td>{_number(r['output_tokens'], 'd')}</td>"
            f"<td class=\"primary\">{_money(r['total_cost'])}</td>"
            f"<td>{r['failed_attempts']}</td>"
            "</tr>"
        )
    known = [r["total_cost"] for r in rows if r["total_cost"] is not None]
    total = (
        '<tr class="total"><td>All providers</td><td></td>'
        f"<td>{sum(r['successful_calls'] for r in rows)}</td>"
        f"<td>{sum(r['input_tokens'] or 0 for r in rows)}</td>"
        f"<td>{sum(r['output_tokens'] or 0 for r in rows)}</td>"
        f"<td>{_money(sum(known) if known else None)}</td>"
        f"<td>{sum(r['failed_attempts'] for r in rows)}</td>"
        "</tr>"
    )
    table = f'<div class="table-wrap"><table>{header}{"".join(body)}{total}</table></div>'
    return _page(intro + table, "/spend", real=True)


def build_spend_page(db_path: Path, window: str, now: datetime) -> str:
    start, end = window_bounds(window, now)
    rows = spend_by_model(db_path, DATA["real"], start=start, end=end)
    return render_spend_page(rows, window, start, end)


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlsplit(self.path)
        if url.path == "/requests":
            try:
                data = parse_requests_query(url.query)
            except ValueError:
                self._send_html(400, render_invalid_query_page())
                return
            requests = load_recent_requests(self.server.db_path, DATA[data], RECENT_REQUESTS)
            self._send_html(200, render_requests_page(requests, data))
            return
        if url.path == "/spend":
            try:
                window = parse_spend_query(url.query)
            except ValueError:
                self._send_html(400, render_invalid_query_page())
                return
            now = datetime.now(timezone.utc)
            self._send_html(200, build_spend_page(self.server.db_path, window, now))
            return
        if url.path != "/":
            self.send_error(404)
            return
        try:
            window, metric = parse_query(url.query)
        except ValueError:
            self._send_html(400, render_invalid_query_page())
            return
        now = datetime.now(timezone.utc)
        self._send_html(200, build_page(self.server.db_path, window, metric, now))

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
