"""JSON API v1: machine-readable representation of analytics results.

Turns `analytics` results into JSON-ready structures (dicts, lists, numbers,
strings, None) for the read-only endpoint `GET /api/v1/metrics`. It is the
machine counterpart of `dashboard`: both consume the same analytics results,
loaded through `query`, but this module never formats for humans. Numbers stay
numbers, unknown facts stay None (JSON null, never 0, "—" or "unknown"), and
times are ISO 8601 UTC strings (`timestamp`).

    JSON request -> web (HTTP) -> api (this module) -> analytics -> storage

It computes no statistics (percentiles and success rates come from
`analytics`), reads no storage directly, and imports no web framework; `web`
turns its results into HTTP responses.

Compatibility: v1 field names, meanings, units and types are a contract once
the endpoint is relied on. Adding a field is compatible; renaming, removing,
or changing a field's type, unit or meaning is not, and would need /api/v2/.
"""

import datetime
import pathlib

from llm_metrics import analytics
from llm_metrics import outcomes
from llm_metrics import query

API_VERSION = "v1"

# Error codes. The message never contains a submitted value.
INVALID_QUERY = "invalid_query"


def timestamp(moment: datetime.datetime) -> str:
    """Serializes an aware datetime as ISO 8601 UTC with microseconds.

    Example: "2026-10-30T12:34:56.789012Z". Every time in the API uses this one
    format, which matches how `recorded_at` is stored.
    """
    utc = moment.astimezone(datetime.timezone.utc)
    return utc.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _reliability(reliability: dict | None) -> dict:
    """Serializes the observed success rate over all attempts.

    Counts are always present (0 is a true count when there were no attempts);
    the rates are None when there were no attempts, rather than 0 or 1.
    """
    if reliability is None:
        return {
            "attempts": 0,
            "successes": 0,
            "failures": 0,
            "success_rate": None,
            "failure_rate": None,
            "failures_by_category": dict.fromkeys(
                outcomes.FAILURE_CATEGORIES, 0
            ),
        }
    return {
        "attempts": reliability["attempts"],
        "successes": reliability["successes"],
        "failures": reliability["failures"],
        "success_rate": reliability["success_rate"],
        "failure_rate": reliability["failure_rate"],
        "failures_by_category": dict(reliability["failures_by_category"]),
    }


def _samples(summary: analytics.MetricSummary | None) -> dict:
    """Serializes the successful observations' summary.

    `count` is always present; the other fields are None when there are no
    observations, never an invented 0.
    """
    if summary is None:
        return {
            "count": 0,
            "first_recorded_at": None,
            "latest": None,
            "percentiles": None,
        }
    return {
        "count": summary.count,
        "first_recorded_at": timestamp(summary.first_at),
        "latest": {
            "recorded_at": timestamp(summary.latest_at),
            "value": summary.latest_value,
        },
        "percentiles": {
            f"p{p}": value for p, value in summary.percentiles.items()
        },
    }


def metrics_response(
    result: analytics.MetricWindow, window: str, metric: str
) -> dict:
    """Builds the /api/v1/metrics body from one aggregate metric window.

    Args:
        result: Analytics for the aggregate population, window, and metric.
        window: Selected window name (a key of `query.WINDOWS`).
        metric: Selected metric name (a key of `query.METRICS`).

    Returns:
        The response body; see `prompts/014d-output.md` for every field.
    """
    _, unit = query.METRICS[metric]
    return {
        "api_version": API_VERSION,
        "population": {
            "data": query.AGGREGATE_DATA,
            "provider": query.AGGREGATE_PROVIDER,
            "model": query.AGGREGATE_MODEL,
        },
        "metric": {"name": metric, "unit": unit},
        "window": {
            "name": window,
            "start": timestamp(result.start),
            "end": timestamp(result.end),
        },
        "samples": _samples(result.summary),
        "reliability": _reliability(result.reliability),
    }


def load_metrics_response(
    db_path: pathlib.Path, window: str, metric: str, now: datetime.datetime
) -> dict:
    """Loads the aggregate metric window and builds its response body."""
    result = query.load_aggregate_metric(db_path, window, metric, now)
    return metrics_response(result, window, metric)


def invalid_query_response() -> dict:
    """Builds the 400 body for /api/v1/metrics, listing the valid values.

    The rejected value is deliberately absent, so it can never be echoed.
    """
    return error_response(
        INVALID_QUERY,
        "Each query parameter must appear at most once, with a valid value.",
        valid={
            "metric": list(query.METRICS),
            "window": list(query.WINDOWS),
        },
        defaults={
            "metric": query.DEFAULT_METRIC,
            "window": query.DEFAULT_WINDOW,
        },
    )


def error_response(code: str, message: str, **details) -> dict:
    """Builds an API error body: {"api_version", "error": {"code", ...}}.

    Args:
        code: Stable machine-readable code, e.g. "invalid_query" or
            "not_found".
        message: Fixed human-readable text; never a submitted value, stack
            trace, or provider message.
        **details: Additional fixed fields of the error object.
    """
    return {
        "api_version": API_VERSION,
        "error": {"code": code, "message": message, **details},
    }
