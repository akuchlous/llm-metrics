"""Model prices and per-request cost. The only place prices are defined.

Prices are in USD per 1,000,000 tokens, in the provider's own token units.
Costs are computed from a request's reported token counts and stored with the
rates used, so a historical request stays explainable after a price change.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Price:
    input_per_1m: float   # USD per 1M input tokens
    output_per_1m: float  # USD per 1M output tokens


# SIMULATED prices for the dummy provider. Not any real provider's pricing.
PRICES = {
    ("dummy", "dummy-model-v1"): Price(input_per_1m=2.00, output_per_1m=8.00),
}


def price_for(provider: str, model: str) -> Price:
    """Current price for a provider/model. Raises KeyError if none is defined."""
    try:
        return PRICES[(provider, model)]
    except KeyError:
        raise KeyError(f"No price defined for provider {provider!r}, model {model!r}.") from None


def request_cost(input_tokens: int, output_tokens: int, price: Price) -> dict:
    """Unrounded USD costs for one request: input_cost, output_cost, total_cost."""
    input_cost = input_tokens * price.input_per_1m / 1_000_000
    output_cost = output_tokens * price.output_per_1m / 1_000_000
    return {
        "input_cost": input_cost,
        "output_cost": output_cost,
        "total_cost": input_cost + output_cost,
    }
