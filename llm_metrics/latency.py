"""Measurement of one streamed request: TTFT, total latency, and output throughput."""

import time

from llm_metrics.providers import LLMProvider

# Every metric this module produces: name -> (display label, unit of `value`).
# The metric name fixes the unit; never store a different unit under a name.
METRICS = {
    "ttft": ("TTFT", "ms"),
    "total_latency": ("Total latency", "ms"),
    "output_chunks_per_s": ("Output throughput", "chunks/s"),
}


def measure_request(provider: LLMProvider, prompt: str) -> list[dict]:
    """Stream one response (one provider call, fully consumed) and return its results.

    All timings start just before `stream()` is called.

    - ttft: until the first item of any kind is received (unchanged since Step 001).
    - total_latency: until the stream is fully consumed.
    - output_chunks_per_s: output throughput after the first chunk, where a chunk
      is one non-empty item yielded by `stream()` (for DummyProvider, one simulated
      token; not a provider/API token count):

          (non-empty chunks - 1) / (time of last non-empty chunk - time of first)

      Omitted when undefined: fewer than 2 non-empty chunks, or no time elapsed
      between the first and last chunk.

    Each result is {"provider", "model", "metric", "value"}; the unit of `value`
    is METRICS[metric][1]. Raises RuntimeError if the stream yields nothing.
    """
    request_started = time.perf_counter()
    first_item_at = None
    first_chunk_at = last_chunk_at = None
    chunks = 0
    for item in provider.stream(prompt):
        now = time.perf_counter()
        if first_item_at is None:
            first_item_at = now
        if item:
            chunks += 1
            if first_chunk_at is None:
                first_chunk_at = now
            last_chunk_at = now
    stream_finished = time.perf_counter()

    if first_item_at is None:
        raise RuntimeError(f"Provider {provider.name!r} returned no tokens.")

    def result(metric: str, value: float) -> dict:
        return {"provider": provider.name, "model": provider.model, "metric": metric, "value": value}

    results = [
        result("ttft", (first_item_at - request_started) * 1000),
        result("total_latency", (stream_finished - request_started) * 1000),
    ]
    if chunks >= 2 and last_chunk_at > first_chunk_at:
        results.append(result("output_chunks_per_s", (chunks - 1) / (last_chunk_at - first_chunk_at)))
    return results
