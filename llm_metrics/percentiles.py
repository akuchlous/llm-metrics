"""Percentiles using the nearest-rank method.

For n values sorted ascending, the p-th percentile is the value at 1-based rank
ceil(p * n / 100). Nearest-rank is used instead of interpolation because the
result is always a latency that was actually observed, is deterministic, and
does not depend on input order. With few values the high percentiles equal the
maximum (e.g. p99 of fewer than 100 values is the largest value).
"""

from collections.abc import Iterable


def percentile(values: Iterable[float], p: int) -> float:
    """Returns the nearest-rank p-th percentile of `values`.

    Args:
        values: Observed values, in any order. Must not be empty.
        p: Percentile as an integer from 1 to 100.

    Returns:
        One of the input values.

    Raises:
        ValueError: If `p` is outside 1..100 or `values` is empty.
    """
    if not 1 <= p <= 100:
        raise ValueError(f"Percentile must be between 1 and 100, got {p}.")
    ordered = sorted(values)
    if not ordered:
        raise ValueError("Cannot compute a percentile of no values.")
    # ceil(p * n / 100) in integer arithmetic, avoiding float rounding errors.
    rank = (p * len(ordered) + 99) // 100
    return ordered[rank - 1]
