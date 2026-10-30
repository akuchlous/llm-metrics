"""Benchmark attempt outcomes and the observed success rate.

Every attempt (one provider call) has exactly one outcome: `SUCCESS` or one of
the stable internal failure categories in `FAILURE_CATEGORIES`. Provider
adapters map their native errors to these categories at the provider boundary
(see `providers.ProviderFailure`), so stored data and analytics never depend on
provider-specific error wording.

This module owns the vocabulary and the rate arithmetic only; it does not read
storage or know about providers.
"""

SUCCESS = "success"

# Failure category -> human-readable label. The keys are stored in the
# database, so they must never be renamed; labels may change freely.
FAILURE_CATEGORIES = {
    "timeout": "Timeout",
    "rate_limited": "Rate limited",
    "provider_error": "Provider/server error",
    "transport_error": "Network/transport error",
    "invalid_response": "Invalid response",
}

OUTCOMES = (SUCCESS, *FAILURE_CATEGORIES)


def success_rate(counts: dict[str, int]) -> dict | None:
    """Computes the observed benchmark success rate from outcome counts.

    Every attempt counts in the denominator, successful or not. This is what
    our runner observed, not a provider's overall uptime.

    Args:
        counts: Number of attempts per outcome, e.g. {"success": 9,
            "timeout": 1}. Outcomes that are absent count as zero.

    Returns:
        None when there are no attempts (no rate, rather than a misleading 0% or
        100%). Otherwise a dict with "attempts", "successes", "failures",
        "success_rate" and "failure_rate" (fractions in 0..1), and
        "failures_by_category" ({category: attempts} for every category).
    """
    attempts = sum(counts.values())
    if attempts == 0:
        return None
    successes = counts.get(SUCCESS, 0)
    failures = attempts - successes
    return {
        "attempts": attempts,
        "successes": successes,
        "failures": failures,
        "success_rate": successes / attempts,
        "failure_rate": failures / attempts,
        "failures_by_category": {
            category: counts.get(category, 0) for category in FAILURE_CATEGORIES
        },
    }
