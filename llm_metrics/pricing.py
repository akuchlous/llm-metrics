"""Model prices and per-request cost. The only place prices are defined.

Prices are in USD per 1,000,000 tokens, in the provider's own token units.
Each saved request stores the rates used for its cost, so a historical cost
stays explainable after a price here changes; there is no price history.
"""

import dataclasses


@dataclasses.dataclass(frozen=True)
class Price:
    """Standard-tier token prices for one provider/model.

    Attributes:
        input_per_1m: USD per 1M input tokens.
        output_per_1m: USD per 1M output tokens.
    """

    input_per_1m: float
    output_per_1m: float


PRICES = {
    # SIMULATED prices for the dummy provider. Not any real provider's pricing.
    ("dummy", "dummy-model-v1"): Price(input_per_1m=2.00, output_per_1m=8.00),
    # OpenAI gpt-6-luna, standard tier (synchronous API; not batch, priority,
    # cached-input, or cache-write rates). Source in PRICE_PROVENANCE.
    ("openai", "gpt-6-luna"): Price(input_per_1m=0.10, output_per_1m=0.50),
}

# Where each real price came from: (provider, model) -> (source, verified on).
# A verification date of None means the price is not yet verified against the
# official source; real_smoke then warns before spending money.
PRICE_PROVENANCE = {
    ("openai", "gpt-6-luna"): (
        "https://developers.openai.com/api/docs/pricing (standard tier)",
        "2026-10-30",
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
    input_tokens: int, output_tokens: int, price: Price
) -> dict[str, float]:
    """Computes the USD cost of one request from its token counts.

    All input tokens are charged at the standard input rate; cached-input
    discounts are not modelled.

    Args:
        input_tokens: Provider-reported input tokens.
        output_tokens: Provider-reported output tokens.
        price: Rates to apply.

    Returns:
        Unrounded "input_cost", "output_cost", and "total_cost" in USD. Values
        are rounded only for display.
    """
    input_cost = input_tokens * price.input_per_1m / 1_000_000
    output_cost = output_tokens * price.output_per_1m / 1_000_000
    return {
        "input_cost": input_cost,
        "output_cost": output_cost,
        "total_cost": input_cost + output_cost,
    }
