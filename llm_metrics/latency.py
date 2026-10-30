"""Latency measurement for one streamed request: TTFT and total response latency."""

import time

from llm_metrics.providers import LLMProvider


def measure_latency(provider: LLMProvider, prompt: str) -> tuple[dict, dict]:
    """Stream one response and return (ttft, total_latency) results.

    Both are timed from the same request start (just before `stream()` is
    called). TTFT stops at the first token; total latency stops when the stream
    is fully consumed. The provider is called exactly once.

    Each result has the schema:
        provider  (str)   provider name, e.g. "dummy"
        model     (str)   model name, e.g. "dummy-model-v1"
        metric    (str)   "ttft" or "total_latency"
        value_ms  (float) milliseconds
    """
    request_started = time.perf_counter()
    first_token_received = None
    for _token in provider.stream(prompt):
        if first_token_received is None:
            first_token_received = time.perf_counter()
    stream_finished = time.perf_counter()

    if first_token_received is None:
        raise RuntimeError(f"Provider {provider.name!r} returned no tokens.")

    def result(metric: str, finished: float) -> dict:
        return {
            "provider": provider.name,
            "model": provider.model,
            "metric": metric,
            "value_ms": (finished - request_started) * 1000,
        }

    return result("ttft", first_token_received), result("total_latency", stream_finished)
