"""Percentiles using the nearest-rank method.

For n values sorted ascending, the p-th percentile is the value at 1-based rank
ceil(p * n / 100). The result is always an observed value, is deterministic,
and does not depend on input order. With few values the high percentiles equal
the maximum (e.g. p99 of fewer than 100 values is the largest value).
"""

from collections.abc import Iterable


def percentile(values: Iterable[float], p: int) -> float:
    """Nearest-rank percentile. p is an integer in 1..100; values must be non-empty."""
    if not 1 <= p <= 100:
        raise ValueError(f"Percentile must be between 1 and 100, got {p}.")
    ordered = sorted(values)
    if not ordered:
        raise ValueError("Cannot compute a percentile of no values.")
    rank = (p * len(ordered) + 99) // 100  # ceil(p * n / 100) in integer arithmetic
    return ordered[rank - 1]
