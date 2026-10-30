"""Benchmark attempt outcomes and the observed success rate.

Every attempt (one provider call) has exactly one outcome: "success" or one of
the stable internal failure categories below. Provider adapters map their
native errors to these categories (see providers.ProviderFailure); analytics
never depend on provider-specific error wording.
"""

SUCCESS = "success"

# Failure category -> display label.
FAILURE_CATEGORIES = {
    "timeout": "Timeout",
    "rate_limited": "Rate limited",
    "provider_error": "Provider/server error",
    "transport_error": "Network/transport error",
    "invalid_response": "Invalid response",
}

OUTCOMES = (SUCCESS, *FAILURE_CATEGORIES)


def success_rate(counts: dict[str, int]) -> dict | None:
    """Observed benchmark success rate from outcome counts ({outcome: attempts}).

    attempts = all attempts; successes = outcome "success"; failures = the rest;
    success_rate = successes / attempts; failure_rate = failures / attempts.
    Returns None when there are no attempts (no rate, rather than 0% or 100%).
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
        "failures_by_category": {c: counts.get(c, 0) for c in FAILURE_CATEGORIES},
    }
