"""Dashboard pages: query semantics and view preparation.

Sits between the HTTP boundary and analytics:

    web (Flask routes, Jinja) -> dashboard (this module) -> analytics -> storage

It owns:

- Query semantics: which query values are valid, what each window name
  means, and which population each page shows (the aggregate page: simulated
  dummy data; requests: the chosen "simulated" or "real" population; spend:
  real data, fixed by `analytics`).
- View preparation: turning `analytics` results (natural values) into
  template-ready dictionaries: formatted numbers, "—" for unknown values,
  "unknown" for unknown cost, human-readable UTC times, navigation links,
  page labels, and the chart's SVG coordinates.

It does not compute statistics or read storage (that is `analytics`), and it
builds no HTML (the Jinja templates in `llm_metrics/templates/` do, with
autoescaping). It imports neither Flask nor Jinja.

Each page has a pure `*_view` function (an analytics result in, a view out)
and a `load_*_view` function that asks `analytics` for the result first:

- Aggregate (`aggregate.html`): success rate over all attempts, then one
  metric over successful attempts as percentiles and a line chart.
- Recent requests (`requests.html`): individual attempts of one population.
- Benchmark API Spend (`spend.html`): llm-metrics' own real API spend.
- Invalid query (`invalid_query.html`): the valid values, never the rejected
  one.
"""

from collections.abc import Mapping, Sequence
import datetime
import math
import pathlib

from llm_metrics import analytics
from llm_metrics import latency
from llm_metrics import outcomes
from llm_metrics import providers

# The aggregate page shows simulated observations from the dummy provider only.
ENVIRONMENT = analytics.SIMULATED_ENVIRONMENT
PROVIDER = providers.DummyProvider.name
MODEL = providers.DummyProvider.model

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

RECENT_REQUESTS = 20  # Rows on the requests page.

# Data populations: query value -> stored environment.
DATA = {
    "simulated": analytics.SIMULATED_ENVIRONMENT,
    "real": analytics.REAL_ENVIRONMENT,
}
DEFAULT_DATA = "simulated"

# Spend accumulates slowly, so its default window is the longest one.
SPEND_DEFAULT_WINDOW = "30d"

# Chart geometry in SVG units (the SVG scales to the page width).
WIDTH, HEIGHT = 800, 300
LEFT, RIGHT, TOP, BOTTOM = 60, 20, 20, 40

# Shown for any fact that is unknown (None), so it is never mistaken for 0.
UNKNOWN = "—"

# Parsed query parameters: name -> every value submitted for it, in order.
# Keeping all values (not just the last) is what lets a repeated parameter be
# rejected instead of silently picking one.
QueryParams = Mapping[str, list[str]]


# Query semantics.


def _parse_choice(params: QueryParams, name: str, choices, default: str) -> str:
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


def parse_query(params: QueryParams) -> tuple[str, str]:
    """Validates the aggregate page's query; other parameters are ignored.

    Args:
        params: Query parameters, including blank values.

    Returns:
        (window, metric), using the defaults for absent parameters.

    Raises:
        ValueError: For an unknown, empty, or repeated window or metric.
    """
    window = _parse_choice(params, "window", WINDOWS, DEFAULT_WINDOW)
    metric = _parse_choice(params, "metric", latency.METRICS, DEFAULT_METRIC)
    return window, metric


def parse_requests_query(params: QueryParams) -> str:
    """Validates the requests page's query.

    Args:
        params: Query parameters, including blank values.

    Returns:
        The data population: "simulated" or "real".

    Raises:
        ValueError: For an unknown, empty, or repeated value.
    """
    return _parse_choice(params, "data", DATA, DEFAULT_DATA)


def parse_spend_query(params: QueryParams) -> str:
    """Validates the spend page's query.

    Args:
        params: Query parameters, including blank values.

    Returns:
        The window name (default `SPEND_DEFAULT_WINDOW`).

    Raises:
        ValueError: For an unknown, empty, or repeated value.
    """
    return _parse_choice(params, "window", WINDOWS, SPEND_DEFAULT_WINDOW)


def window_bounds(
    window: str, now: datetime.datetime
) -> tuple[datetime.datetime, datetime.datetime]:
    """Returns (start, end) of the named window ending at `now`; inclusive."""
    return analytics.window_bounds(WINDOWS[window], now)


# Display formatting: the only place analytics values become text.


def _display_time(moment: datetime.datetime) -> str:
    return f"{moment:%Y-%m-%d %H:%M} UTC"


def _window_label(start: datetime.datetime, end: datetime.datetime) -> dict:
    return {"start": _display_time(start), "end": _display_time(end)}


def _number(value: float | None, spec: str) -> str:
    """Formats a number, or `UNKNOWN` when it is unknown (never shown as 0)."""
    return UNKNOWN if value is None else format(value, spec)


def _text(value: str | None) -> str:
    """Returns stored text, or `UNKNOWN` when it is None."""
    return UNKNOWN if value is None else value


def _money(value: float | None) -> str:
    """Formats USD, or "unknown" when no cost is known (never $0)."""
    return "unknown" if value is None else f"${value:.6f}"


def _percent(fraction: float) -> str:
    return f"{fraction * 100:.1f}"


def _layout(active_view: str | None, real_data: bool) -> dict:
    """Returns the facts the shared layout (`base.html`) needs.

    Args:
        active_view: Path of the current page, marked in the navigation, or
            None when no page is current.
        real_data: Whether the page shows real-provider data (blue label)
            rather than simulated data (orange label).
    """
    return {
        "active_view": active_view,
        "real_data": real_data,
        "simulated_provider": PROVIDER,
        "simulated_model": MODEL,
    }


def _link(href: str, text: str, current: bool) -> dict:
    return {"href": href, "text": text, "current": current}


def _aggregate_links(window: str | None, metric: str | None) -> dict:
    """Builds the metric and window links of the aggregate page.

    Each link keeps the other current selection, so switching the window does
    not reset the metric and vice versa. None means nothing is current.
    """
    keep_metric = metric or DEFAULT_METRIC
    keep_window = window or DEFAULT_WINDOW
    return {
        "metric_links": [
            _link(
                f"/?window={keep_window}&metric={name}", label, name == metric
            )
            for name, (label, _) in latency.METRICS.items()
        ],
        "window_links": [
            _link(f"/?window={name}&metric={keep_metric}", name, name == window)
            for name in WINDOWS
        ],
    }


def _chart(
    observations: Sequence[analytics.Observation],
    start: datetime.datetime,
    end: datetime.datetime,
) -> dict:
    """Computes this dashboard's SVG line-chart geometry.

    The x axis spans the full window and is proportional to time, so gaps in
    the data are visible. All coordinates are numbers or number-formatted
    strings; `_chart.html` only places them in SVG elements, so the template
    stays free of calculations.

    Args:
        observations: Non-empty successful observations, oldest first.
        start: Window start (left edge).
        end: Window end (right edge).

    Returns:
        SVG coordinates: viewBox size, axis and label positions, the y-axis
        maximum, the polyline points, and the latest point.
    """
    t_min, t_max = start.timestamp(), end.timestamp()
    times = [
        observation.recorded_at.timestamp() for observation in observations
    ]
    values = [observation.value for observation in observations]
    # Headroom above the largest value, rounded up to a whole 100 units, and
    # never 0, so the axis label stays readable and the line never touches the
    # top edge.
    y_max = max(100, math.ceil(max(values) * 1.1 / 100) * 100)

    def x(t: float) -> float:
        return LEFT + (t - t_min) / (t_max - t_min) * (WIDTH - LEFT - RIGHT)

    def y(v: float) -> float:
        return HEIGHT - BOTTOM - v / y_max * (HEIGHT - TOP - BOTTOM)

    return {
        "width": WIDTH,
        "height": HEIGHT,
        "left": LEFT,
        "right_edge": WIDTH - RIGHT,
        "top": TOP,
        "axis_bottom": HEIGHT - BOTTOM,
        # Text positions: y-axis numbers sit just left of the axis, the unit
        # just right of it, and the time labels below the plot.
        "axis_label_x": LEFT - 6,
        "unit_label_x": LEFT + 6,
        "top_label_y": TOP + 4,
        "time_label_y": HEIGHT - 15,
        "y_max": f"{y_max:.0f}",
        "points": " ".join(
            f"{x(t):.1f},{y(v):.1f}" for t, v in zip(times, values)
        ),
        "latest_x": f"{x(times[-1]):.1f}",
        "latest_y": f"{y(values[-1]):.1f}",
    }


# Aggregate page.


def _reliability_view(reliability: dict | None) -> dict | None:
    """Words the observed success rate (all attempts) for display."""
    if reliability is None:
        return None
    return {
        "success_percent": _percent(reliability["success_rate"]),
        "failure_percent": _percent(reliability["failure_rate"]),
        "successes": reliability["successes"],
        "failures": reliability["failures"],
        "attempts": reliability["attempts"],
        "failures_by_category": [
            {
                "label": label,
                "attempts": reliability["failures_by_category"][category],
            }
            for category, label in outcomes.FAILURE_CATEGORIES.items()
        ],
    }


def _summary_view(result: analytics.MetricWindow, unit: str) -> dict | None:
    """Words a metric summary and adds the chart, or None if empty."""
    summary = result.summary
    if summary is None:
        return None
    return {
        "latest_value": f"{summary.latest_value:.1f} {unit}",
        "latest_time": _display_time(summary.latest_at),
        "first_time": _display_time(summary.first_at),
        "count": summary.count,
        "percentiles": [
            {"name": f"p{p}", "value": f"{value:.1f} {unit}"}
            for p, value in summary.percentiles.items()
        ],
        "chart": _chart(result.observations, result.start, result.end),
    }


def aggregate_view(
    result: analytics.MetricWindow, window: str, metric: str
) -> dict:
    """Prepares the aggregate page from one metric window.

    Args:
        result: Analytics for the selected population, window, and metric.
        window: Selected window name.
        metric: Selected metric name.

    Returns:
        View data for `aggregate.html`. "summary" is None when the window has
        no successful observations of the metric; "reliability" is None when
        it has no attempts.
    """
    label, unit = latency.METRICS[metric]
    return {
        **_layout("/", real_data=False),
        **_aggregate_links(window, metric),
        "window": window,
        "window_label": _window_label(result.start, result.end),
        "metric_label": label,
        "unit": unit,
        "reliability": _reliability_view(result.reliability),
        "summary": _summary_view(result, unit),
    }


def load_aggregate_view(
    db_path: pathlib.Path, window: str, metric: str, now: datetime.datetime
) -> dict:
    """Loads the aggregate page's analytics and prepares its view."""
    start, end = window_bounds(window, now)
    result = analytics.load_metric_window(
        db_path, ENVIRONMENT, PROVIDER, MODEL, metric, start=start, end=end
    )
    return aggregate_view(result, window, metric)


def invalid_query_view() -> dict:
    """Prepares the view listing every valid query value.

    The rejected value is deliberately not part of the view, so it can never
    be echoed back.
    """
    return {
        **_layout(None, real_data=False),
        **_aggregate_links(None, None),
        "windows": list(WINDOWS),
        "default_window": DEFAULT_WINDOW,
        "spend_default_window": SPEND_DEFAULT_WINDOW,
        "metrics": list(latency.METRICS),
        "default_metric": DEFAULT_METRIC,
        "data_values": list(DATA),
        "default_data": DEFAULT_DATA,
    }


# Requests page.


def _origin(cloud: str | None, region: str | None) -> str:
    if cloud is None and region is None:
        return UNKNOWN
    return f"{_text(cloud)} / {_text(region)}"


def _request_row(attempt: dict) -> dict:
    """Words one attempt for the requests table.

    Unknown values (failed attempts, older rows) become `UNKNOWN`, never 0.
    """
    metrics = attempt["metrics"]
    failed = attempt["outcome"] != outcomes.SUCCESS
    return {
        "time": _display_time(attempt["recorded_at"]),
        "id": attempt["id"],
        "short_id": attempt["id"][:8],
        "failed": failed,
        "outcome": (
            outcomes.FAILURE_CATEGORIES.get(
                attempt["outcome"], attempt["outcome"]
            )
            if failed
            else "success"
        ),
        "total_latency": _number(metrics.get("total_latency"), ".1f"),
        "ttft": _number(metrics.get("ttft"), ".1f"),
        "tokens_per_s": _number(metrics.get("output_tokens_per_s"), ".1f"),
        "chunks_per_s": _number(metrics.get("output_chunks_per_s"), ".1f"),
        "input_tokens": _number(attempt["input_tokens"], "d"),
        "output_tokens": _number(attempt["output_tokens"], "d"),
        "max_output_tokens": f"{attempt['requested_max_output_tokens']:d}",
        "total_cost": _number(attempt["total_cost"], ".6f"),
        "input_cost": _number(attempt["input_cost"], ".6f"),
        "output_cost": _number(attempt["output_cost"], ".6f"),
        "failed_after": _number(attempt["failed_after_ms"], ".1f"),
        "provider": attempt["provider"],
        "model": attempt["model"],
        "workload": _text(attempt["workload_id"]),
        "origin": _origin(attempt["origin_cloud"], attempt["origin_region"]),
        "cache_policy": _text(attempt["cache_policy"]),
        "cached_input_tokens": _number(attempt["cached_input_tokens"], "d"),
    }


def requests_view(attempts: list[dict], data: str = DEFAULT_DATA) -> dict:
    """Prepares the requests page for one data population.

    Args:
        attempts: Attempts as `analytics.load_recent_attempts` returns them,
            newest first.
        data: "simulated" or "real"; selects the label and explanations.

    Returns:
        View data for `requests.html`.
    """
    return {
        **_layout("/requests", real_data=data == "real"),
        "data_links": [
            _link(f"/requests?data={name}", name, name == data) for name in DATA
        ],
        "recent_limit": RECENT_REQUESTS,
        "rows": [_request_row(attempt) for attempt in attempts],
    }


def load_requests_view(db_path: pathlib.Path, data: str) -> dict:
    """Loads the most recent attempts of one population; see `requests_view`.

    Args:
        db_path: Database to read.
        data: "simulated" or "real" (see `DATA`).
    """
    attempts = analytics.load_recent_attempts(
        db_path, DATA[data], RECENT_REQUESTS
    )
    return requests_view(attempts, data)


# Spend page.


def _spend_group_row(group: dict) -> dict:
    return {
        "provider": group["provider"],
        "model": group["model"],
        "successful_calls": group["successful_calls"],
        "input_tokens": _number(group["input_tokens"], "d"),
        "output_tokens": _number(group["output_tokens"], "d"),
        "total_cost": _money(group["total_cost"]),
        "failed_attempts": group["failed_attempts"],
    }


def _spend_totals_row(totals: analytics.SpendTotals | None) -> dict | None:
    if totals is None:
        return None
    return {
        "successful_calls": totals.successful_calls,
        "input_tokens": totals.input_tokens,
        "output_tokens": totals.output_tokens,
        "total_cost": _money(totals.total_cost),
        "failed_attempts": totals.failed_attempts,
    }


def spend_view(spend: analytics.Spend, window: str) -> dict:
    """Prepares the Benchmark API Spend page (real data only).

    Args:
        spend: Spend analytics for the window.
        window: Selected window name.

    Returns:
        View data for `spend.html`. "total" is None when there are no groups.
    """
    return {
        **_layout("/spend", real_data=True),
        "window": window,
        "window_label": _window_label(spend.start, spend.end),
        "window_links": [
            _link(f"/spend?window={name}", name, name == window)
            for name in WINDOWS
        ],
        "rows": [_spend_group_row(group) for group in spend.groups],
        "total": _spend_totals_row(spend.totals),
    }


def load_spend_view(
    db_path: pathlib.Path, window: str, now: datetime.datetime
) -> dict:
    """Loads real-data spend for a window; see `spend_view`."""
    start, end = window_bounds(window, now)
    spend = analytics.load_benchmark_spend(db_path, start=start, end=end)
    return spend_view(spend, window)
