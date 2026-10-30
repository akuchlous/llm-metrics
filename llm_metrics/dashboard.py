"""Local metrics dashboard: server-rendered HTML pages, no JavaScript.

Usage: python -m llm_metrics.dashboard   (serves http://127.0.0.1:8000/)

Routes:

- `GET /?window=24h|7d|30d&metric=<name>`: for a window ending now (default
  7d), the observed benchmark success rate of all attempts, then one metric
  (default ttft; any key of `latency.METRICS`) over successful attempts as
  percentiles and a line chart. Simulated data only.
- `GET /requests?data=simulated|real`: the most recent individual attempts of
  one data population (default simulated).
- `GET /spend?window=24h|7d|30d`: Benchmark API Spend, the known API token cost
  of llm-metrics' own real benchmark requests per provider/model (default
  30d).

Any unknown, empty, or repeated query value returns HTTP 400 without echoing
the value. Simulated and real data are never shown on the same page, and every
page is labelled with its population.

Security: binds to 127.0.0.1 only and sends a Content-Security-Policy that
allows no scripts or external loads. Every value read from storage is
HTML-escaped. Uses only the standard library.
"""

import datetime
import html
import http.server
import math
import pathlib
import sys
import urllib.parse

from llm_metrics import config
from llm_metrics import latency
from llm_metrics import outcomes
from llm_metrics import percentiles
from llm_metrics import providers
from llm_metrics import storage

HOST = "127.0.0.1"

# The aggregate page shows simulated observations from the dummy provider only.
ENVIRONMENT = "test"
PROVIDER = providers.DummyProvider.name
MODEL = providers.DummyProvider.model
PERCENTILES = (50, 95, 99)

DEFAULT_METRIC = "ttft"

# Selectable windows, each ending at the current UTC time. The default is 7d:
# with hourly data it holds ~168 observations, enough for nearest-rank p99 to
# differ from the maximum (24h would hold only ~24).
WINDOWS = {
    "24h": datetime.timedelta(hours=24),
    "7d": datetime.timedelta(days=7),
    "30d": datetime.timedelta(days=30),
}
DEFAULT_WINDOW = "7d"

RECENT_REQUESTS = 20  # Rows on the /requests page.

# Data populations: query value -> stored environment.
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
  body {{ font-family: system-ui, sans-serif; max-width: 900px;
    margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; background: #fff; }}
  .label {{ display: inline-block; background: #b45309; color: #fff;
    font-weight: 700; padding: .3rem .7rem; border-radius: 4px;
    letter-spacing: .05em; }}
  .latest {{ font-size: 2rem; font-weight: 700; margin: .2rem 0; }}
  .muted {{ color: #555; }}
  .percentiles {{ font-size: 1.15rem; }}
  svg {{ width: 100%; height: auto; border: 1px solid #ddd; }}
  nav a {{ margin-right: .8rem; }}
  nav a[aria-current] {{ font-weight: 700; color: #1a1a1a;
    text-decoration: none; }}
  .views {{ margin-bottom: 1rem; }}
  .table-wrap {{ overflow-x: auto; }}
  table {{ border-collapse: collapse; font-size: .85rem; }}
  th, td {{ padding: .3rem .45rem; border-bottom: 1px solid #ddd;
    text-align: right; white-space: nowrap; }}
  th {{ white-space: normal; vertical-align: bottom; }}
  th:first-child, td:first-child, th:nth-child(2), td:nth-child(2),
  th:nth-child(3), td:nth-child(3),
  th:last-child, td:last-child {{ text-align: left; }}
  .primary {{ font-weight: 700; }}
  .failed {{ color: #b91c1c; font-weight: 700; }}
  .reliability {{ border: 1px solid #ddd; padding: .2rem 1rem .6rem;
    margin: 1rem 0; }}
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

VIEWS = {
    "/": "Aggregate",
    "/requests": "Recent requests",
    "/spend": "Benchmark API Spend",
}

SIMULATED_HEADER = (
    '<p class="label">TEST / SIMULATED DATA</p>\n'
    f"<p>Provider: <b>{html.escape(PROVIDER)}</b>"
    f" · Model: <b>{html.escape(MODEL)}</b></p>\n"
    '<p class="muted">Simulated observations from the dummy provider.'
    " Not real LLM performance.</p>"
)
REAL_HEADER = (
    '<p class="label real">REAL PROVIDER DATA</p>\n'
    '<p class="muted">Real API calls made by llm-metrics\' own benchmark'
    " runner. Never mixed with simulated data.</p>"
)


def _page(body: str, view: str | None, real: bool = False) -> str:
    """Wraps a page body in the shared layout.

    Args:
        body: Page-specific HTML (already escaped).
        view: Path of the current view, marked in the navigation, or None.
        real: Whether to show the real-provider data label instead of the
            simulated one.

    Returns:
        A complete HTML document.
    """
    links = []
    for path, name in VIEWS.items():
        current = ' aria-current="page"' if path == view else ""
        links.append(f'<a href="{path}"{current}>{name}</a>')
    views = f'<nav class="views" aria-label="View">{"".join(links)}</nav>'
    data_header = REAL_HEADER if real else SIMULATED_HEADER
    return PAGE.format(views=views, data_header=data_header, body=body)


def _parse_time(recorded_at: str) -> datetime.datetime:
    return datetime.datetime.strptime(
        recorded_at, "%Y-%m-%dT%H:%M:%S.%fZ"
    ).replace(tzinfo=datetime.timezone.utc)


def _display_time(recorded_at: str) -> str:
    return _parse_time(recorded_at).strftime("%Y-%m-%d %H:%M UTC")


def _chart_svg(
    observations: list[tuple[str, float]],
    label: str,
    unit: str,
    start: datetime.datetime,
    end: datetime.datetime,
) -> str:
    """Draws a line chart of values over the whole window.

    The x axis spans the full window and is proportional to time, so gaps in
    the data are visible; the latest point is marked.

    Args:
        observations: Non-empty (recorded_at, value) pairs, oldest first.
        label: Metric label, used for the accessible name.
        unit: Unit shown on the y axis.
        start: Window start (left edge).
        end: Window end (right edge).

    Returns:
        An inline SVG element.
    """
    t_min, t_max = start.timestamp(), end.timestamp()
    times = [_parse_time(t).timestamp() for t, _ in observations]
    values = [v for _, v in observations]
    # Headroom above the largest value, rounded up to a whole 100 units, and
    # never 0, so the axis label stays readable and the line never touches the
    # top edge.
    y_max = max(100, math.ceil(max(values) * 1.1 / 100) * 100)

    def x(t: float) -> float:
        return LEFT + (t - t_min) / (t_max - t_min) * (WIDTH - LEFT - RIGHT)

    def y(v: float) -> float:
        return HEIGHT - BOTTOM - v / y_max * (HEIGHT - TOP - BOTTOM)

    points = " ".join(f"{x(t):.1f},{y(v):.1f}" for t, v in zip(times, values))
    axis_bottom = HEIGHT - BOTTOM
    return (
        f'<svg viewBox="0 0 {WIDTH} {HEIGHT}" role="img"'
        f' aria-label="{label} over time">\n'
        f'  <line x1="{LEFT}" y1="{TOP}" x2="{LEFT}" y2="{axis_bottom}"'
        ' stroke="#999"/>\n'
        f'  <line x1="{LEFT}" y1="{axis_bottom}" x2="{WIDTH - RIGHT}"'
        f' y2="{axis_bottom}" stroke="#999"/>\n'
        f'  <text x="{LEFT - 6}" y="{TOP + 4}" text-anchor="end"'
        f' font-size="12">{y_max:.0f}</text>\n'
        f'  <text x="{LEFT - 6}" y="{axis_bottom}" text-anchor="end"'
        ' font-size="12">0</text>\n'
        f'  <text x="{LEFT + 6}" y="{TOP + 4}" font-size="12"'
        f' fill="#555">{unit}</text>\n'
        f'  <text x="{LEFT}" y="{HEIGHT - 15}" font-size="12">'
        f"{start:%Y-%m-%d %H:%M} UTC</text>\n"
        f'  <text x="{WIDTH - RIGHT}" y="{HEIGHT - 15}" text-anchor="end"'
        f' font-size="12">{end:%Y-%m-%d %H:%M} UTC (now)</text>\n'
        '  <polyline fill="none" stroke="#2563eb" stroke-width="1.5"'
        f' points="{points}"/>\n'
        f'  <circle cx="{x(times[-1]):.1f}" cy="{y(values[-1]):.1f}" r="4"'
        ' fill="#2563eb"/>\n'
        "</svg>"
    )


def _nav(window: str | None, metric: str | None) -> str:
    """Builds the metric and window links of the aggregate page.

    Each link keeps the other current selection, so switching the window does
    not reset the metric and vice versa. None means nothing is current.
    """
    keep_metric = metric or DEFAULT_METRIC
    keep_window = window or DEFAULT_WINDOW

    def link(
        href_window: str, href_metric: str, text: str, current: bool
    ) -> str:
        aria = ' aria-current="page"' if current else ""
        return (
            f'<a href="/?window={href_window}&amp;metric={href_metric}"'
            f"{aria}>{text}</a>"
        )

    windows = "".join(
        link(name, keep_metric, name, name == window) for name in WINDOWS
    )
    metrics = "".join(
        link(keep_window, name, label, name == metric)
        for name, (label, _) in latency.METRICS.items()
    )
    return (
        f'<nav aria-label="Metric">Metric: {metrics}</nav>\n'
        f'<nav aria-label="Time window">Window: {windows}</nav>'
    )


def _parse_choice(
    params: dict[str, list[str]], name: str, choices, default: str
) -> str:
    """Returns the single allowed value of query parameter `name`.

    Raises:
        ValueError: If the value is not in `choices`, is empty, or is repeated.
            The message never includes the submitted value.
    """
    values = params.get(name)
    if values is None:
        return default
    if len(values) != 1 or values[0] not in choices:
        raise ValueError(f"Invalid {name}.")
    return values[0]


def parse_query(query: str) -> tuple[str, str]:
    """Parses the aggregate page's query string; other parameters are ignored.

    Returns:
        (window, metric), using the defaults for absent parameters.

    Raises:
        ValueError: For an unknown, empty, or repeated window or metric.
    """
    params = urllib.parse.parse_qs(query, keep_blank_values=True)
    window = _parse_choice(params, "window", WINDOWS, DEFAULT_WINDOW)
    metric = _parse_choice(params, "metric", latency.METRICS, DEFAULT_METRIC)
    return window, metric


def window_bounds(
    window: str, now: datetime.datetime
) -> tuple[datetime.datetime, datetime.datetime]:
    """Returns (start, end) of `window` ending at `now`; both are inclusive."""
    return now - WINDOWS[window], now


def _reliability_section(outcome_counts: dict[str, int], window: str) -> str:
    """Renders the observed success rate over all attempts in the window."""
    title = f"<h2>Observed benchmark success rate ({window})</h2>\n"
    scope = (
        '<p class="muted">All benchmark attempts made by this runner in the'
        " window, successful or not. This is what our runner observed, not"
        " the provider's overall uptime.</p>\n"
    )
    rate = outcomes.success_rate(outcome_counts)
    if rate is None:
        body = (
            "<p><b>No benchmark attempts in the selected window"
            f" ({window})</b>, so no success rate.</p>"
        )
    else:
        failures = "".join(
            f"<tr><td>{label}</td>"
            f"<td>{rate['failures_by_category'][category]}</td></tr>"
            for category, label in outcomes.FAILURE_CATEGORIES.items()
        )
        body = (
            f'<p class="latest">{rate["success_rate"] * 100:.1f}%</p>\n'
            f"<p>{rate['successes']} of {rate['attempts']} attempts succeeded"
            f" ({rate['failures']} failed,"
            f" {rate['failure_rate'] * 100:.1f}%).</p>\n"
            "<table><tr><th>Failure category</th><th>Attempts</th></tr>"
            f"{failures}</table>"
        )
    return f'<section class="reliability">{title}{scope}{body}</section>\n'


def render_page(
    observations: list[tuple[str, float]],
    window: str,
    metric: str,
    start: datetime.datetime,
    end: datetime.datetime,
    outcome_counts: dict[str, int],
) -> str:
    """Renders the aggregate page for one window and metric.

    The success rate covers every attempt, while every metric figure (count,
    latest value, percentiles, chart) comes from `observations` alone, which
    hold successful measurements only. Failed attempts therefore lower the
    success rate without adding fabricated zero latencies.

    Args:
        observations: (recorded_at, value) pairs of `metric`, oldest first.
        window: Selected window name.
        metric: Selected metric name.
        start: Inclusive window start.
        end: Inclusive window end (now).
        outcome_counts: {outcome: attempts} in the window.

    Returns:
        A complete HTML document.
    """
    label, unit = latency.METRICS[metric]
    header = (
        _nav(window, metric)
        + f'\n<p class="muted">Window {window}: {start:%Y-%m-%d %H:%M} UTC'
        f" to {end:%Y-%m-%d %H:%M} UTC (now), inclusive.</p>\n"
        + _reliability_section(outcome_counts, window)
        + f"<h2>{label} (successful attempts only)</h2>\n"
    )
    if not observations:
        body = (
            f"<p><b>No {label} observations in the selected window"
            f" ({window}).</b> Run <code>./run.sh</code> to record one, or"
            " choose a longer window.</p>"
        )
    else:
        latest_at, latest_value = observations[-1]
        values = [v for _, v in observations]
        count = len(observations)
        summary = " · ".join(
            f"p{p} <b>{percentiles.percentile(values, p):.1f} {unit}</b>"
            for p in PERCENTILES
        )
        plural = "" if count == 1 else "s"
        body = (
            f'<p class="muted">Latest {label}'
            f" ({_display_time(latest_at)})</p>\n"
            f'<p class="latest">{latest_value:.1f} {unit}</p>\n'
            f'<p class="percentiles">{label} {summary}'
            f' <span class="muted">(nearest-rank, n = {count})</span></p>\n'
            f'<p class="muted">{count} observation{plural} in window,'
            f" first {_display_time(observations[0][0])},"
            f" latest {_display_time(latest_at)}.</p>\n"
            + _chart_svg(observations, label, unit, start, end)
        )
    return _page(header + body, "/")


def render_invalid_query_page() -> str:
    """Renders the page for an invalid query value, listing the valid ones.

    The submitted value is never echoed back.
    """
    body = (
        _nav(None, None)
        + "\n<p><b>Invalid window or metric</b> (or data) value. Windows: "
        + ", ".join(WINDOWS)
        + f" (default {DEFAULT_WINDOW}; {SPEND_DEFAULT_WINDOW} on Benchmark"
        " API Spend). Metrics: "
        + ", ".join(latency.METRICS)
        + f" (default {DEFAULT_METRIC}). Data on Recent requests: "
        + ", ".join(DATA)
        + f" (default {DEFAULT_DATA}).</p>"
    )
    return _page(body, None)


def build_page(
    db_path: pathlib.Path, window: str, metric: str, now: datetime.datetime
) -> str:
    """Loads one metric and the outcome counts for a window and renders them."""
    start, end = window_bounds(window, now)
    observations = storage.load_observations(
        db_path, ENVIRONMENT, PROVIDER, MODEL, metric, start=start, end=end
    )
    counts = storage.count_outcomes(
        db_path, ENVIRONMENT, PROVIDER, MODEL, start=start, end=end
    )
    return render_page(observations, window, metric, start, end, counts)


def _number(value: float | None, spec: str) -> str:
    """Formats a number, or "—" when unknown (never shown as 0)."""
    return "—" if value is None else format(value, spec)


def _data_nav(selected: str | None) -> str:
    links = []
    for name in DATA:
        current = ' aria-current="page"' if name == selected else ""
        links.append(f'<a href="/requests?data={name}"{current}>{name}</a>')
    return f'<nav aria-label="Data">Data: {"".join(links)}</nav>\n'


def parse_requests_query(query: str) -> str:
    """Returns the /requests data population: "simulated" or "real".

    Raises:
        ValueError: For an unknown, empty, or repeated value.
    """
    return _parse_choice(
        urllib.parse.parse_qs(query, keep_blank_values=True),
        "data",
        DATA,
        DEFAULT_DATA,
    )


def _text(value: str | None) -> str:
    """Escapes stored text, or returns "—" when it is unknown (NULL)."""
    return "—" if value is None else html.escape(value)


def _origin(cloud: str | None, region: str | None) -> str:
    if cloud is None and region is None:
        return "—"
    return f"{_text(cloud)} / {_text(region)}"


_REQUESTS_TABLE_HEADER = (
    "<tr><th>Time (UTC)</th><th>Request</th><th>Outcome</th>"
    "<th>Total latency (ms)</th><th>TTFT (ms)</th>"
    "<th>Throughput (tokens/s)</th><th>Throughput (chunks/s)</th>"
    "<th>Input tokens</th><th>Output tokens</th><th>Max output tokens</th>"
    "<th>Total cost ($)</th><th>Input cost ($)</th><th>Output cost ($)</th>"
    "<th>Failed after (ms)</th><th>Provider / model</th><th>Workload</th>"
    "<th>Origin</th><th>Cache policy</th><th>Cached input tokens</th></tr>"
)


def _request_row(request: dict) -> str:
    """Renders one request as a table row matching `_REQUESTS_TABLE_HEADER`.

    Unknown values (failed attempts, older rows) show as "—", never as 0.
    """
    metrics = request["metrics"]
    if request["outcome"] == outcomes.SUCCESS:
        outcome = "success"
    else:
        failure_label = html.escape(
            outcomes.FAILURE_CATEGORIES.get(
                request["outcome"], request["outcome"]
            )
        )
        outcome = f'<span class="failed">FAILED</span>: {failure_label}'
    request_id = html.escape(request["id"])
    origin = _origin(request["origin_cloud"], request["origin_region"])
    cells = (
        f"<td>{_display_time(request['recorded_at'])}</td>",
        f'<td><code title="{request_id}">{request_id[:8]}</code></td>',
        f"<td>{outcome}</td>",
        '<td class="primary">'
        f"{_number(metrics.get('total_latency'), '.1f')}</td>",
        f"<td>{_number(metrics.get('ttft'), '.1f')}</td>",
        f"<td>{_number(metrics.get('output_tokens_per_s'), '.1f')}</td>",
        f"<td>{_number(metrics.get('output_chunks_per_s'), '.1f')}</td>",
        f"<td>{_number(request['input_tokens'], 'd')}</td>",
        f"<td>{_number(request['output_tokens'], 'd')}</td>",
        f"<td>{request['requested_max_output_tokens']:d}</td>",
        f'<td class="primary">{_number(request["total_cost"], ".6f")}</td>',
        f"<td>{_number(request['input_cost'], '.6f')}</td>",
        f"<td>{_number(request['output_cost'], '.6f')}</td>",
        f"<td>{_number(request['failed_after_ms'], '.1f')}</td>",
        f"<td>{html.escape(request['provider'])}"
        f" / {html.escape(request['model'])}</td>",
        f"<td>{_text(request['workload_id'])}</td>",
        f"<td>{origin}</td>",
        f"<td>{_text(request['cache_policy'])}</td>",
        f"<td>{_number(request['cached_input_tokens'], 'd')}</td>",
    )
    return "<tr>" + "".join(cells) + "</tr>"


def render_requests_page(requests: list[dict], data: str = DEFAULT_DATA) -> str:
    """Renders the table of individual attempts of one data population.

    Args:
        requests: Requests as returned by `storage.load_recent_requests`,
            newest first.
        data: "simulated" or "real"; selects the label and explanations.

    Returns:
        A complete HTML document.
    """
    real = data == "real"
    if real:
        accounting = (
            " Token counts are reported by the provider; costs use the rates"
            " stored with each request (USD)."
        )
        empty = (
            "No real benchmark attempts yet. Run"
            " <code>python -m llm_metrics.real_smoke</code> (one paid request)."
        )
    else:
        accounting = (
            " Token counts use a <b>simulated</b> tokenizer and costs use"
            " <b>simulated</b> prices (USD); they do not match any real"
            " provider."
        )
        empty = (
            "No benchmark attempts yet. Run <code>./run.sh</code> to record"
            " one. (Observations recorded before Step 010 have no request"
            " details.)"
        )
    intro = (
        f"<h2>Recent requests</h2>\n{_data_nav(data)}"
        f'<p class="muted">The {RECENT_REQUESTS} most recent benchmark'
        f" attempts, successful or failed.{accounting} Total latency is a"
        " successful request's response time; TTFT is shown for streaming"
        " diagnostics. Token throughput is the provider's output token count"
        " divided by the time from the first to the last output chunk (TTFT"
        " excluded); chunk throughput counts stream chunks, not tokens."
        " <i>Workload</i> is the benchmark case that was run; <i>Origin</i> is"
        " where the benchmark runner executed (cloud / region), not where the"
        " provider served it. <i>Cache policy</i> is what the request asked of"
        " the provider's prompt cache (<i>disabled</i>: uncached / cold-ish;"
        " <i>provider_default</i> or <i>unknown</i>: not established);"
        " <i>Cached input</i> is the provider-reported cached input tokens (—"
        " = not reported, which is not zero). For failed attempts, tokens,"
        " cost, and performance are unknown (—); <i>Failed after</i> is the"
        " time until the failure was detected.</p>\n"
    )
    if not requests:
        return _page(intro + f"<p><b>{empty}</b></p>", "/requests", real)
    # Most important columns first (time, latency, tokens, total cost); the
    # table scrolls sideways on narrow screens.
    rows = "".join(_request_row(request) for request in requests)
    table = (
        f'<div class="table-wrap"><table>{_REQUESTS_TABLE_HEADER}{rows}'
        "</table></div>"
    )
    return _page(intro + table, "/requests", real)


def parse_spend_query(query: str) -> str:
    """Returns the /spend window (default `SPEND_DEFAULT_WINDOW`).

    Raises:
        ValueError: For an unknown, empty, or repeated value.
    """
    return _parse_choice(
        urllib.parse.parse_qs(query, keep_blank_values=True),
        "window",
        WINDOWS,
        SPEND_DEFAULT_WINDOW,
    )


def _money(value: float | None) -> str:
    """Formats USD, or "unknown" when no cost is known (never $0)."""
    return "unknown" if value is None else f"${value:.6f}"


def render_spend_page(
    rows: list[dict],
    window: str,
    start: datetime.datetime,
    end: datetime.datetime,
) -> str:
    """Renders Benchmark API Spend for one window (real data only).

    Args:
        rows: Groups as returned by `storage.spend_by_model`.
        window: Selected window name.
        start: Inclusive window start.
        end: Inclusive window end (now).

    Returns:
        A complete HTML document. The grand total sums known costs only.
    """
    links = []
    for name in WINDOWS:
        current = ' aria-current="page"' if name == window else ""
        links.append(f'<a href="/spend?window={name}"{current}>{name}</a>')
    intro = (
        "<h2>Benchmark API Spend</h2>\n"
        f'<nav aria-label="Time window">Window: {"".join(links)}</nav>\n'
        f'<p class="muted">Window {window}: {start:%Y-%m-%d %H:%M} UTC to'
        f" {end:%Y-%m-%d %H:%M} UTC (now), inclusive.</p>\n"
        "<p>This is <b>the API token cost incurred by llm-metrics to run its"
        " own benchmark requests</b>, from the token counts each provider"
        " reported and the rates stored with each request (USD). It is"
        " <b>not</b> the provider's revenue, not what every user pays, not"
        " hosting or infrastructure cost, and not a workload-independent"
        " price comparison. Only real provider requests are included;"
        " simulated data never is.</p>\n"
        '<p class="muted">Spend counts successful calls only. A failed'
        " attempt's cost is unknown (a provider may still have billed part of"
        " it), so it is counted under <i>Failed attempts</i>, never added as"
        " $0.</p>\n"
    )
    if not rows:
        return _page(
            intro + "<p><b>No real benchmark attempts in the selected window"
            f" ({window}).</b></p>",
            "/spend",
            real=True,
        )
    header = (
        "<tr><th>Provider</th><th>Model</th><th>Successful paid calls</th>"
        "<th>Input tokens</th><th>Output tokens</th><th>Total cost</th>"
        "<th>Failed attempts (cost unknown)</th></tr>"
    )
    body = []
    for row in rows:
        body.append(
            "<tr>"
            f"<td>{html.escape(row['provider'])}</td>"
            f"<td>{html.escape(row['model'])}</td>"
            f"<td>{row['successful_calls']}</td>"
            f"<td>{_number(row['input_tokens'], 'd')}</td>"
            f"<td>{_number(row['output_tokens'], 'd')}</td>"
            f'<td class="primary">{_money(row["total_cost"])}</td>'
            f"<td>{row['failed_attempts']}</td>"
            "</tr>"
        )
    known = [row["total_cost"] for row in rows if row["total_cost"] is not None]
    total = (
        '<tr class="total"><td>All providers</td><td></td>'
        f"<td>{sum(row['successful_calls'] for row in rows)}</td>"
        f"<td>{sum(row['input_tokens'] or 0 for row in rows)}</td>"
        f"<td>{sum(row['output_tokens'] or 0 for row in rows)}</td>"
        f"<td>{_money(sum(known) if known else None)}</td>"
        f"<td>{sum(row['failed_attempts'] for row in rows)}</td>"
        "</tr>"
    )
    table = (
        f'<div class="table-wrap"><table>{header}{"".join(body)}{total}'
        "</table></div>"
    )
    return _page(intro + table, "/spend", real=True)


def build_spend_page(
    db_path: pathlib.Path, window: str, now: datetime.datetime
) -> str:
    """Loads real-data spend for a window and renders the spend page."""
    start, end = window_bounds(window, now)
    rows = storage.spend_by_model(db_path, DATA["real"], start=start, end=end)
    return render_spend_page(rows, window, start, end)


class _Handler(http.server.BaseHTTPRequestHandler):
    """Routes GET requests to the three pages; anything else is a 404.

    Reads the database path from `self.server.db_path` (set by `make_server`).
    """

    # The standard library dispatches to methods named do_<HTTP method>.
    def do_GET(self):  # pylint: disable=invalid-name
        url = urllib.parse.urlsplit(self.path)
        if url.path == "/requests":
            try:
                data = parse_requests_query(url.query)
            except ValueError:
                self._send_html(400, render_invalid_query_page())
                return
            requests = storage.load_recent_requests(
                self.server.db_path, DATA[data], RECENT_REQUESTS
            )
            self._send_html(200, render_requests_page(requests, data))
            return
        if url.path == "/spend":
            try:
                window = parse_spend_query(url.query)
            except ValueError:
                self._send_html(400, render_invalid_query_page())
                return
            now = datetime.datetime.now(datetime.timezone.utc)
            self._send_html(
                200, build_spend_page(self.server.db_path, window, now)
            )
            return
        if url.path != "/":
            self.send_error(404)
            return
        try:
            window, metric = parse_query(url.query)
        except ValueError:
            self._send_html(400, render_invalid_query_page())
            return
        now = datetime.datetime.now(datetime.timezone.utc)
        self._send_html(
            200, build_page(self.server.db_path, window, metric, now)
        )

    def _send_html(self, status: int, page: str) -> None:
        body = page.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        # The pages have no scripts and load nothing external, so the policy
        # blocks everything except their inline styles.
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; style-src 'unsafe-inline'",
        )
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def make_server(db_path: pathlib.Path, port: int) -> http.server.HTTPServer:
    """Creates, but does not start, the dashboard server on 127.0.0.1.

    Args:
        db_path: Database the pages read from.
        port: Port to bind; 0 picks any free port (see `server_address`).

    Raises:
        OSError: If the port cannot be bound.
    """
    server = http.server.HTTPServer((HOST, port), _Handler)
    server.db_path = db_path
    return server


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
        server = make_server(config.get_db_path(), port)
    except OSError as e:  # Most often: the port is already in use.
        print(
            f"Error: cannot serve the dashboard on {HOST}:{port}"
            f" ({e.strerror}). Is it already running? Set LLM_METRICS_PORT to"
            " use another port.",
            file=sys.stderr,
        )
        return 1
    # The real port matters when port 0 was requested; run.sh and tests read
    # it from this line.
    bound_port = server.server_address[1]
    print(
        f"Dashboard: http://{HOST}:{bound_port}/  (Ctrl+C to stop)", flush=True
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
