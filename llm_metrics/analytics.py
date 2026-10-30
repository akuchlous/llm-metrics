"""Product analytics over stored benchmark data, as natural values.

Owns the interpretation of stored facts: which population each result is
computed over, the observed success rate, nearest-rank percentile summaries,
and benchmark API spend totals. It reads only through `storage` (no SQL here)
and returns plain values: floats, ints, aware datetimes, and None for unknown.
It never formats for display ("—", "$0.000034", "2026-10-30 12:00 UTC" belong
to the presentation layer, `dashboard`), so any consumer, such as the
dashboard, a future JSON API, or a report, can reuse the same results.

Population rules (each function's contract restates the one it applies):

- Observed success/failure rates count every benchmark attempt (request) in
  the population and window, successful or failed.
- Metric distributions (latest value, percentiles, chart points) use
  successful observations only: a failed attempt has no metric observations,
  so it never contributes a fabricated zero latency or throughput.
- Simulated ("test") and real-provider ("prod") data are separate
  environments; no function here mixes them.
- Benchmark API spend covers real-provider attempts only, summing the stored
  costs of successful attempts; a failed attempt's cost is unknown and is
  counted, never added as $0.

Dependency direction: dashboard -> analytics -> storage. This module imports
no web framework.
"""

from collections.abc import Sequence
import dataclasses
import datetime
import pathlib

from llm_metrics import outcomes
from llm_metrics import percentiles
from llm_metrics import storage

# Stored environments: simulated (dummy provider) and real-provider data.
SIMULATED_ENVIRONMENT = "test"
REAL_ENVIRONMENT = "prod"

PERCENTILES = (50, 95, 99)


@dataclasses.dataclass(frozen=True)
class Observation:
    """One successful metric measurement.

    Attributes:
        recorded_at: When it was recorded (aware, UTC).
        value: The measured value, in the unit fixed by its metric.
    """

    recorded_at: datetime.datetime
    value: float


@dataclasses.dataclass(frozen=True)
class MetricSummary:
    """Summary of a non-empty set of successful observations.

    Attributes:
        count: Number of observations.
        first_at: Time of the oldest observation.
        latest_at: Time of the newest observation.
        latest_value: Value of the newest observation.
        percentiles: Nearest-rank percentile -> value, for `PERCENTILES`.
    """

    count: int
    first_at: datetime.datetime
    latest_at: datetime.datetime
    latest_value: float
    percentiles: dict[int, float]


@dataclasses.dataclass(frozen=True)
class MetricWindow:
    """One metric for one provider/model population over a time window.

    The two populations differ on purpose: `reliability` counts every attempt,
    while `observations` and `summary` hold successful measurements only.

    Attributes:
        start: Inclusive window start.
        end: Inclusive window end.
        observations: Successful observations of the metric, oldest first.
        summary: Their summary, or None when there are none.
        reliability: `outcomes.success_rate` over all attempts in the window,
            or None when there were no attempts.
    """

    start: datetime.datetime
    end: datetime.datetime
    observations: tuple[Observation, ...]
    summary: MetricSummary | None
    reliability: dict | None


@dataclasses.dataclass(frozen=True)
class SpendTotals:
    """Benchmark API spend summed over all provider/model groups.

    Attributes:
        successful_calls: Successful (paid) attempts.
        input_tokens: Input tokens of successful attempts.
        output_tokens: Output tokens of successful attempts.
        total_cost: Sum of known costs in USD, or None when no cost is known
            (never 0 for "unknown").
        failed_attempts: Failed attempts, whose cost is unknown.
    """

    successful_calls: int
    input_tokens: int
    output_tokens: int
    total_cost: float | None
    failed_attempts: int


@dataclasses.dataclass(frozen=True)
class Spend:
    """Benchmark API spend for a window (real-provider data only).

    Attributes:
        start: Inclusive window start.
        end: Inclusive window end.
        groups: One dict per provider/model, as `storage.spend_by_model`
            returns them (costs and tokens of successful attempts; None when
            unknown).
        totals: Totals over all groups, or None when there are no groups.
    """

    start: datetime.datetime
    end: datetime.datetime
    groups: tuple[dict, ...]
    totals: SpendTotals | None


def parse_recorded_at(recorded_at: str) -> datetime.datetime:
    """Converts stored `recorded_at` text to an aware UTC datetime."""
    return datetime.datetime.strptime(
        recorded_at, "%Y-%m-%dT%H:%M:%S.%fZ"
    ).replace(tzinfo=datetime.timezone.utc)


def window_bounds(
    duration: datetime.timedelta, now: datetime.datetime
) -> tuple[datetime.datetime, datetime.datetime]:
    """Returns (start, end) of a window of `duration` ending at `now`.

    Both bounds are inclusive.
    """
    return now - duration, now


def summarize_metric(
    observations: Sequence[Observation],
) -> MetricSummary | None:
    """Summarizes successful observations with nearest-rank percentiles.

    Args:
        observations: Successful observations, oldest first.

    Returns:
        None when there are no observations (no figure is invented);
        otherwise the count, first and latest times, latest value, and
        nearest-rank percentiles for `PERCENTILES`.
    """
    if not observations:
        return None
    values = [observation.value for observation in observations]
    return MetricSummary(
        count=len(observations),
        first_at=observations[0].recorded_at,
        latest_at=observations[-1].recorded_at,
        latest_value=observations[-1].value,
        percentiles={p: percentiles.percentile(values, p) for p in PERCENTILES},
    )


def load_metric_window(
    db_path: pathlib.Path,
    environment: str,
    provider: str,
    model: str,
    metric: str,
    *,
    start: datetime.datetime,
    end: datetime.datetime,
) -> MetricWindow:
    """Loads one metric and the attempt outcomes for a population and window.

    Args:
        db_path: Database to read.
        environment: `SIMULATED_ENVIRONMENT` or `REAL_ENVIRONMENT`.
        provider: Provider name.
        model: Model name.
        metric: A key of `latency.METRICS`.
        start: Inclusive window start.
        end: Inclusive window end.

    Returns:
        The window's successful observations with their summary, and the
        observed success rate over all attempts (see `MetricWindow`).
    """
    observations = tuple(
        Observation(parse_recorded_at(recorded_at), value)
        for recorded_at, value in storage.load_observations(
            db_path, environment, provider, model, metric, start=start, end=end
        )
    )
    attempt_counts = storage.count_outcomes(
        db_path, environment, provider, model, start=start, end=end
    )
    return MetricWindow(
        start=start,
        end=end,
        observations=observations,
        summary=summarize_metric(observations),
        reliability=outcomes.success_rate(attempt_counts),
    )


def load_recent_attempts(
    db_path: pathlib.Path, environment: str, limit: int
) -> list[dict]:
    """Loads the most recent attempts of one environment, newest first.

    Args:
        db_path: Database to read.
        environment: `SIMULATED_ENVIRONMENT` or `REAL_ENVIRONMENT`; the two
            are never mixed.
        limit: Maximum number of attempts.

    Returns:
        Attempts as `storage.load_recent_requests` returns them (unknown
        facts are None), with `recorded_at` converted to an aware datetime.
    """
    return [
        {**request, "recorded_at": parse_recorded_at(request["recorded_at"])}
        for request in storage.load_recent_requests(db_path, environment, limit)
    ]


def spend_totals(groups: Sequence[dict]) -> SpendTotals | None:
    """Totals spend groups; known costs only.

    Args:
        groups: Provider/model groups as `storage.spend_by_model` returns
            them.

    Returns:
        None when there are no groups. Otherwise the totals, where
        `total_cost` sums only the groups with a known cost and is None when
        no group has one: unknown cost is never counted as $0.
    """
    if not groups:
        return None
    known_costs = [
        group["total_cost"]
        for group in groups
        if group["total_cost"] is not None
    ]
    return SpendTotals(
        successful_calls=sum(group["successful_calls"] for group in groups),
        input_tokens=sum(group["input_tokens"] or 0 for group in groups),
        output_tokens=sum(group["output_tokens"] or 0 for group in groups),
        total_cost=sum(known_costs) if known_costs else None,
        failed_attempts=sum(group["failed_attempts"] for group in groups),
    )


def load_benchmark_spend(
    db_path: pathlib.Path,
    *,
    start: datetime.datetime,
    end: datetime.datetime,
) -> Spend:
    """Loads llm-metrics' own API spend for a window, real-provider data only.

    Simulated (dummy) costs are never included: the population is fixed to
    `REAL_ENVIRONMENT`.
    """
    groups = tuple(
        storage.spend_by_model(db_path, REAL_ENVIRONMENT, start=start, end=end)
    )
    return Spend(
        start=start, end=end, groups=groups, totals=spend_totals(groups)
    )
