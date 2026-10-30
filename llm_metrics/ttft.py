"""Time To First Token (TTFT) measurement."""

import time

from llm_metrics.providers import LLMProvider


def measure_ttft(provider: LLMProvider, prompt: str) -> dict:
    """Return the time from starting the request to receiving the first token.

    Result schema:
        provider  (str)   provider name, e.g. "dummy"
        model     (str)   model name, e.g. "dummy-model-v1"
        metric    (str)   always "ttft"
        value_ms  (float) TTFT in milliseconds
    """
    request_started = time.perf_counter()
    for _token in provider.stream(prompt):
        first_token_received = time.perf_counter()
        break
    else:
        raise RuntimeError(f"Provider {provider.name!r} returned no tokens.")

    return {
        "provider": provider.name,
        "model": provider.model,
        "metric": "ttft",
        "value_ms": (first_token_received - request_started) * 1000,
    }
