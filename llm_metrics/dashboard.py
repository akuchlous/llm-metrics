"""Dashboard pages: query validation, data loading, and page view data.

This is the application/view layer between the HTTP boundary and storage:

    web (Flask routes, templates) -> dashboard (this module) -> storage

It owns what each page means: which query values are valid, which data
population and time window a page shows, which facts it loads, and how each
fact is worded for display (formatted numbers, "—" for unknown values, link
targets). It returns plain dictionaries ("views") and never builds HTML: the
Jinja templates in `llm_metrics/templates/` turn a view into markup, with
autoescaping. It imports neither Flask nor Jinja.

Every `*_view` function is pure (its inputs are explicit), and every
`load_*_view` function reads storage and then calls it.

Pages:

- Aggregate (`aggregate.html`): for a window ending now (default 7d), the
  observed benchmark success rate of all attempts, then one metric (default
  ttft; any key of `latency.METRICS`) over successful attempts as percentiles
  and a line chart. Simulated data only.
- Recent requests (`requests.html`): the most recent individual attempts of
  one data population ("simulated" or "real"; default simulated).
- Benchmark API Spend (`spend.html`): the known API token cost of
  llm-metrics' own real benchmark requests per provider/model (default 30d).
- Invalid query (`invalid_query.html`): the valid values, never the rejected
  one.

Simulated and real data are never shown on the same page, and every view says
which population it shows.
"""

from collections.abc import Mapping
import datetime
import math
import pathlib

from llm_metrics import latency
from llm_metrics import outcomes
from llm_metrics import percentiles
from llm_metrics import providers
from llm_metrics import storage

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

RECENT_REQUESTS = 20  # Rows on the requests page.

# Data populations: query value -> stored environment.
DATA = {"simulated": "test", "real": "prod"}
DEFAULT_DATA = "simulated"

# Spend accumulates slowly, so its default window is the longest one.
SPEND_DEFAULT_WINDOW = "30d"

# Chart geometry in SVG units (the SVG scales to the page width).
WIDTH, HEIGHT = 800, 300
LEFT, RIGHT, TOP, BOTTOM = 60, 20, 20, 40

# Shown for any fact that is unknown (NULL), so it is never mistaken for 0.
UNKNOWN = "—"

# Parsed query parameters: name -> every value submitted for it, in order.
# Keeping all values (not just the last) is what lets a repeated parameter be
# rejected instead of silently picking one.
QueryParams = Mapping[str, list[str]]


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


def _parse_time(recorded_at: str) -> datetime.datetime:
    return datetime.datetime.strptime(
        recorded_at, "%Y-%m-%dT%H:%M:%S.%fZ"
    ).replace(tzinfo=datetime.timezone.utc)


def _display_time(recorded_at: str) -> str:
    return _parse_time(recorded_at).strftime("%Y-%m-%d %H:%M UTC")


def _window_label(start: datetime.datetime, end: datetime.datetime) -> dict:
    return {
        "start": f"{start:%Y-%m-%d %H:%M} UTC",
        "end": f"{end:%Y-%m-%d %H:%M} UTC",
    }


def _number(value: float | None, spec: str) -> str:
    """Formats a number, or `UNKNOWN` when it is unknown (never shown as 0)."""
    return UNKNOWN if value is None else format(value, spec)


def _text(value: str | None) -> str:
    """Returns stored text, or `UNKNOWN` when it is NULL."""
    return UNKNOWN if value is None else value


def _money(value: float | None) -> str:
    """Formats USD, or "unknown" when no cost is known (never $0)."""
    return "unknown" if value is None else f"${value:.6f}"


def _chart(
    observations: list[tuple[str, float]],
    start: datetime.datetime,
    end: datetime.datetime,
) -> dict:
    """Computes line-chart geometry for values over the whole window.

    The x axis spans the full window and is proportional to time, so gaps in
    the data are visible. All coordinates are numbers or number-formatted
    strings; `chart.html` only places them in SVG elements. Keeping the
    arithmetic here keeps the template free of calculations.

    Args:
        observations: Non-empty (recorded_at, value) pairs, oldest first.
        start: Window start (left edge).
        end: Window end (right edge).

    Returns:
        SVG coordinates: viewBox size, axis positions, the y-axis maximum, the
        polyline points, and the latest point.
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


def _aggregate_links(window: str | None, metric: str | None) -> dict:
    """Builds the metric and window links of the aggregate page.

    Each link keeps the other current selection, so switching the window does
    not reset the metric and vice versa. None means nothing is current.
    """
    keep_metric = metric or DEFAULT_METRIC
    keep_window = window or DEFAULT_WINDOW

    def link(href_window: str, href_metric: str, text: str, current: bool):
        return {
            "href": f"/?window={href_window}&metric={href_metric}",
            "text": text,
            "current": current,
        }

    return {
        "metric_links": [
            link(keep_window, name, label, name == metric)
            for name, (label, _) in latency.METRICS.items()
        ],
        "window_links": [
            link(name, keep_metric, name, name == window) for name in WINDOWS
        ],
    }


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
    """Returns (start, end) of `window` ending at `now`; both are inclusive."""
    return now - WINDOWS[window], now


def _reliability(outcome_counts: dict[str, int]) -> dict | None:
    """Words the observed success rate over all attempts for display.

    Returns:
        None when there are no attempts (no rate is shown); otherwise counts,
        percentages formatted to one decimal, and one (label, attempts) entry
        per failure category.
    """
    rate = outcomes.success_rate(outcome_counts)
    if rate is None:
        return None
    return {
        "success_percent": f"{rate['success_rate'] * 100:.1f}",
        "failure_percent": f"{rate['failure_rate'] * 100:.1f}",
        "successes": rate["successes"],
        "failures": rate["failures"],
        "attempts": rate["attempts"],
        "failures_by_category": [
            {"label": label, "attempts": rate["failures_by_category"][category]}
            for category, label in outcomes.FAILURE_CATEGORIES.items()
        ],
    }


def _metric_summary(
    observations: list[tuple[str, float]],
    unit: str,
    start: datetime.datetime,
    end: datetime.datetime,
) -> dict | None:
    """Summarizes one metric's successful observations, or None if empty.

    Returns:
        The latest value and its time, nearest-rank percentiles, the count,
        the first and latest times, and the chart geometry.
    """
    if not observations:
        return None
    latest_at, latest_value = observations[-1]
    values = [value for _, value in observations]
    return {
        "latest_value": f"{latest_value:.1f} {unit}",
        "latest_time": _display_time(latest_at),
        "first_time": _display_time(observations[0][0]),
        "count": len(observations),
        "percentiles": [
            {
                "name": f"p{p}",
                "value": f"{percentiles.percentile(values, p):.1f} {unit}",
            }
            for p in PERCENTILES
        ],
        "chart": _chart(observations, start, end),
    }


def aggregate_view(
    observations: list[tuple[str, float]],
    window: str,
    metric: str,
    start: datetime.datetime,
    end: datetime.datetime,
    outcome_counts: dict[str, int],
) -> dict:
    """Builds the aggregate page's view for one window and metric.

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
        View data for `aggregate.html`. "summary" is None when the window has
        no observations of the metric; "reliability" is None when it has no
        attempts.
    """
    label, unit = latency.METRICS[metric]
    return {
        **_layout("/", real_data=False),
        **_aggregate_links(window, metric),
        "window": window,
        "window_label": _window_label(start, end),
        "metric_label": label,
        "unit": unit,
        "reliability": _reliability(outcome_counts),
        "summary": _metric_summary(observations, unit, start, end),
    }


def load_aggregate_view(
    db_path: pathlib.Path, window: str, metric: str, now: datetime.datetime
) -> dict:
    """Loads one metric and the outcome counts for a window; see
    `aggregate_view`."""
    start, end = window_bounds(window, now)
    observations = storage.load_observations(
        db_path, ENVIRONMENT, PROVIDER, MODEL, metric, start=start, end=end
    )
    counts = storage.count_outcomes(
        db_path, ENVIRONMENT, PROVIDER, MODEL, start=start, end=end
    )
    return aggregate_view(observations, window, metric, start, end, counts)


def invalid_query_view() -> dict:
    """Builds the view listing every valid query value.

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


def _origin(cloud: str | None, region: str | None) -> str:
    if cloud is None and region is None:
        return UNKNOWN
    return f"{_text(cloud)} / {_text(region)}"


def _request_row(request: dict) -> dict:
    """Words one stored request for the requests table.

    Unknown values (failed attempts, older rows) become `UNKNOWN`, never 0.
    """
    metrics = request["metrics"]
    failed = request["outcome"] != outcomes.SUCCESS
    return {
        "time": _display_time(request["recorded_at"]),
        "id": request["id"],
        "short_id": request["id"][:8],
        "failed": failed,
        "outcome": (
            outcomes.FAILURE_CATEGORIES.get(
                request["outcome"], request["outcome"]
            )
            if failed
            else "success"
        ),
        "total_latency": _number(metrics.get("total_latency"), ".1f"),
        "ttft": _number(metrics.get("ttft"), ".1f"),
        "tokens_per_s": _number(metrics.get("output_tokens_per_s"), ".1f"),
        "chunks_per_s": _number(metrics.get("output_chunks_per_s"), ".1f"),
        "input_tokens": _number(request["input_tokens"], "d"),
        "output_tokens": _number(request["output_tokens"], "d"),
        "max_output_tokens": f"{request['requested_max_output_tokens']:d}",
        "total_cost": _number(request["total_cost"], ".6f"),
        "input_cost": _number(request["input_cost"], ".6f"),
        "output_cost": _number(request["output_cost"], ".6f"),
        "failed_after": _number(request["failed_after_ms"], ".1f"),
        "provider": request["provider"],
        "model": request["model"],
        "workload": _text(request["workload_id"]),
        "origin": _origin(request["origin_cloud"], request["origin_region"]),
        "cache_policy": _text(request["cache_policy"]),
        "cached_input_tokens": _number(request["cached_input_tokens"], "d"),
    }


def requests_view(requests: list[dict], data: str = DEFAULT_DATA) -> dict:
    """Builds the requests page's view for one data population.

    Args:
        requests: Requests as returned by `storage.load_recent_requests`,
            newest first.
        data: "simulated" or "real"; selects the label and explanations.

    Returns:
        View data for `requests.html`.
    """
    return {
        **_layout("/requests", real_data=data == "real"),
        "data_links": [
            {
                "href": f"/requests?data={name}",
                "text": name,
                "current": name == data,
            }
            for name in DATA
        ],
        "recent_limit": RECENT_REQUESTS,
        "rows": [_request_row(request) for request in requests],
    }


def load_requests_view(db_path: pathlib.Path, data: str) -> dict:
    """Loads the most recent attempts of one population; see `requests_view`.

    Args:
        db_path: Database to read.
        data: "simulated" or "real" (see `DATA`).
    """
    requests = storage.load_recent_requests(
        db_path, DATA[data], RECENT_REQUESTS
    )
    return requests_view(requests, data)


def _spend_row(row: dict) -> dict:
    return {
        "provider": row["provider"],
        "model": row["model"],
        "successful_calls": row["successful_calls"],
        "input_tokens": _number(row["input_tokens"], "d"),
        "output_tokens": _number(row["output_tokens"], "d"),
        "total_cost": _money(row["total_cost"]),
        "failed_attempts": row["failed_attempts"],
    }


def _spend_total(rows: list[dict]) -> dict:
    """Totals spend over all groups. Costs sum known values only."""
    known = [row["total_cost"] for row in rows if row["total_cost"] is not None]
    return {
        "successful_calls": sum(row["successful_calls"] for row in rows),
        "input_tokens": sum(row["input_tokens"] or 0 for row in rows),
        "output_tokens": sum(row["output_tokens"] or 0 for row in rows),
        "total_cost": _money(sum(known) if known else None),
        "failed_attempts": sum(row["failed_attempts"] for row in rows),
    }


def spend_view(
    rows: list[dict],
    window: str,
    start: datetime.datetime,
    end: datetime.datetime,
) -> dict:
    """Builds the Benchmark API Spend view for one window (real data only).

    Args:
        rows: Groups as returned by `storage.spend_by_model`.
        window: Selected window name.
        start: Inclusive window start.
        end: Inclusive window end (now).

    Returns:
        View data for `spend.html`. "total" is None when there are no rows.
    """
    return {
        **_layout("/spend", real_data=True),
        "window": window,
        "window_label": _window_label(start, end),
        "window_links": [
            {
                "href": f"/spend?window={name}",
                "text": name,
                "current": name == window,
            }
            for name in WINDOWS
        ],
        "rows": [_spend_row(row) for row in rows],
        "total": _spend_total(rows) if rows else None,
    }


def load_spend_view(
    db_path: pathlib.Path, window: str, now: datetime.datetime
) -> dict:
    """Loads real-data spend for a window; see `spend_view`."""
    start, end = window_bounds(window, now)
    rows = storage.spend_by_model(db_path, DATA["real"], start=start, end=end)
    return spend_view(rows, window, start, end)
