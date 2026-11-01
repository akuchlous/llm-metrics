"""Model prices and per-request cost. The only place prices are defined.

Prices are in USD per 1,000,000 tokens, in the provider's own token units.
Each saved request stores the rates used for its cost (input, output, and the
cached-input rate), so a historical cost stays explainable after a price here
changes; there is no price history.
"""

import dataclasses


@dataclasses.dataclass(frozen=True)
class Price:
    """Standard-tier token prices for one provider/model.

    Attributes:
        input_per_1m: USD per 1M input tokens (not read from a cache).
        output_per_1m: USD per 1M output tokens, which for every real provider
            here includes billed reasoning/thinking tokens.
        cached_input_per_1m: USD per 1M input tokens the provider reports it
            read from its prompt cache, or None when no cached rate is defined
            (then a request reporting cached tokens cannot be priced).
        max_input_tokens: Largest prompt (input tokens) these rates apply to,
            or None when the provider has one rate for every prompt size.
            Above it the provider bills every token of the request at a higher
            long-context rate, which is not modelled.
    """

    input_per_1m: float
    output_per_1m: float
    cached_input_per_1m: float | None = None
    max_input_tokens: int | None = None


PRICES = {
    # SIMULATED prices for the dummy provider. Not any real provider's pricing.
    ("dummy", "dummy-model-v1"): Price(input_per_1m=2.00, output_per_1m=8.00),
    # Real prices: standard (synchronous) tier only; not batch, flex, priority,
    # or cache-write rates. Sources in PRICE_PROVENANCE.
    ("openai", "gpt-6-luna"): Price(
        input_per_1m=0.10,
        output_per_1m=0.50,
        cached_input_per_1m=0.01,
        max_input_tokens=272_000,  # "Short context: <=272K input tokens".
    ),
    ("anthropic", "claude-haiku-5-5"): Price(
        input_per_1m=0.10,
        output_per_1m=0.50,
        cached_input_per_1m=0.01,  # Cache reads.
        max_input_tokens=100_000,  # "for prompts up to 100,000 tokens".
    ),
    ("google", "gemini-3.5-flash-lite"): Price(
        input_per_1m=0.30,
        output_per_1m=2.50,  # "Output (including thinking)".
        cached_input_per_1m=0.03,  # The "Context caching" rate.
    ),
    ("xai", "grok-4.20-0309-non-reasoning"): Price(
        input_per_1m=1.25,
        output_per_1m=2.50,
        cached_input_per_1m=0.20,
        max_input_tokens=199_999,  # The "<200k prompt tokens" tier.
    ),
}

# Where each real price came from: (provider, model) -> (source, verified on).
# A verification date of None means the price is not yet verified against the
# official source; the real-provider commands then warn before spending money.
PRICE_PROVENANCE = {
    ("openai", "gpt-6-luna"): (
        "https://developers.openai.com/api/docs/pricing (standard tier)",
        "2026-11-01",
    ),
    ("anthropic", "claude-haiku-5-5"): (
        "https://platform.claude.com/docs/en/models/haiku-5-5/overview"
        " (pricing)",
        "2026-11-01",
    ),
    ("google", "gemini-3.5-flash-lite"): (
        "https://ai.google.dev/gemini-api/docs/pricing (standard, paid tier)",
        "2026-11-01",
    ),
    ("xai", "grok-4.20-0309-non-reasoning"): (
        "https://docs.x.ai/docs/models (text API pricing)",
        "2026-11-01",
    ),
}


def price_for(provider: str, model: str) -> Price:
    """Returns the current price for a provider/model.

    Raises:
        KeyError: If no price is defined. Callers look the price up before a
            paid call so a missing price never wastes money.
    """
    try:
        return PRICES[(provider, model)]
    except KeyError:
        raise KeyError(
            f"No price defined for provider {provider!r}, model {model!r}."
        ) from None


def request_cost(
    input_tokens: int,
    output_tokens: int,
    price: Price,
    cached_input_tokens: int | None = None,
) -> dict[str, float]:
    """Computes the USD cost of one request from its token counts.

    Cached input tokens (a part of `input_tokens`) are charged at the cached
    rate only when the provider reported them; unknown (None) cached tokens
    leave every input token at the standard rate, never a guessed discount.

    Args:
        input_tokens: Provider-reported input tokens, including cached ones.
        output_tokens: Provider-reported output tokens.
        price: Rates to apply.
        cached_input_tokens: Provider-reported cached part of `input_tokens`,
            or None when not reported.

    Returns:
        Unrounded "input_cost" (standard and cached input together),
        "output_cost", and "total_cost" in USD. Values are rounded only for
        display.

    Raises:
        ValueError: If cached tokens were reported but `price` has no cached
            rate, so they cannot be priced truthfully.
    """
    cached = cached_input_tokens or 0
    if cached and price.cached_input_per_1m is None:
        raise ValueError("Cached input tokens reported but no cached rate.")
    input_cost = (input_tokens - cached) * price.input_per_1m / 1_000_000
    if cached:
        input_cost += cached * price.cached_input_per_1m / 1_000_000
    output_cost = output_tokens * price.output_per_1m / 1_000_000
    return {
        "input_cost": input_cost,
        "output_cost": output_cost,
        "total_cost": input_cost + output_cost,
    }
