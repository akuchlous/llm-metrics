"""Product query definitions shared by the HTML dashboard and the JSON API.

One place defines what a caller may select and what each selection means, so
the dashboard (`dashboard`) and the JSON API (`api`) cannot drift apart:

- the selectable metrics (`latency.METRICS`, which also fixes each unit),
- the window names and their durations,
- the data populations ("simulated" or "real") and their stored environments,
- the population the aggregate views measure, and
- the validation of query parameters (unknown, empty, or repeated values are
  rejected, and the rejected value is never part of the error).

Presentation (labels, links, number formats, "—") stays in `dashboard`, and
machine representation in `api`. This module imports no web framework.
"""

from collections.abc import Collection, Mapping
import datetime
import pathlib

from llm_metrics import analytics
from llm_metrics import latency
from llm_metrics import providers

# Parsed query parameters: name -> every value submitted for it, in order.
# Keeping all values (not just the last) is what lets a repeated parameter be
# rejected instead of silently picking one.
QueryParams = Mapping[str, list[str]]

# Selectable metrics: name -> (label, unit). The name fixes the unit.
METRICS = latency.METRICS
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

# Data populations: query value -> stored environment.
DATA = {
    "simulated": analytics.SIMULATED_ENVIRONMENT,
    "real": analytics.REAL_ENVIRONMENT,
}
DEFAULT_DATA = "simulated"

# The aggregate views (dashboard page and /api/v1/metrics) measure one fixed
# population: simulated observations from the dummy provider. There is no
# provider/model selector yet.
AGGREGATE_DATA = "simulated"
AGGREGATE_ENVIRONMENT = DATA[AGGREGATE_DATA]
AGGREGATE_PROVIDER = providers.DummyProvider.name
AGGREGATE_MODEL = providers.DummyProvider.model


def parse_choice(
    params: QueryParams, name: str, choices: Collection[str], default: str
) -> str:
    """Returns the single allowed value of query parameter `name`.

    Args:
        params: Query parameters, including blank values.
        name: Parameter to read.
        choices: Allowed values.
        default: Value used when the parameter is absent.

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


def parse_metric_query(params: QueryParams) -> tuple[str, str]:
    """Validates an aggregate metric query; other parameters are ignored.

    Shared by the aggregate page and /api/v1/metrics.

    Args:
        params: Query parameters, including blank values.

    Returns:
        (window, metric), using the defaults for absent parameters.

    Raises:
        ValueError: For an unknown, empty, or repeated window or metric.
    """
    window = parse_choice(params, "window", WINDOWS, DEFAULT_WINDOW)
    metric = parse_choice(params, "metric", METRICS, DEFAULT_METRIC)
    return window, metric


def window_bounds(
    window: str, now: datetime.datetime
) -> tuple[datetime.datetime, datetime.datetime]:
    """Returns (start, end) of the named window ending at `now`; inclusive."""
    return analytics.window_bounds(WINDOWS[window], now)


def load_aggregate_metric(
    db_path: pathlib.Path, window: str, metric: str, now: datetime.datetime
) -> analytics.MetricWindow:
    """Loads one metric window of the aggregate population.

    Both the aggregate page and /api/v1/metrics call this, so they always
    describe the same population with the same analytics.

    Args:
        db_path: Database to read.
        window: A key of `WINDOWS`.
        metric: A key of `METRICS`.
        now: End of the window.
    """
    start, end = window_bounds(window, now)
    return analytics.load_metric_window(
        db_path,
        AGGREGATE_ENVIRONMENT,
        AGGREGATE_PROVIDER,
        AGGREGATE_MODEL,
        metric,
        start=start,
        end=end,
    )
