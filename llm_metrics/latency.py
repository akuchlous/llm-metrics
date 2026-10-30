"""Measurement of one streamed request: token facts, TTFT, total latency, and
output chunk throughput."""

import time

from llm_metrics.providers import LLMProvider, Usage

# Every metric this module produces: name -> (display label, unit of `value`).
# The metric name fixes the unit; never store a different unit under a name.
# Total latency is listed first: it is the primary user-facing latency; TTFT is
# diagnostic (streaming responsiveness).
METRICS = {
    "total_latency": ("Total latency", "ms"),
    "ttft": ("TTFT", "ms"),
    "output_chunks_per_s": ("Output throughput", "chunks/s"),
}


def measure_request(
    provider: LLMProvider, prompt: str, max_output_tokens: int
) -> tuple[dict, list[dict]]:
    """Stream one response (one provider call, fully consumed); return (request, results).

    `request` holds the request's token facts, as reported by the provider's
    final `Usage` item (never derived from chunk counts):
        provider, model, input_tokens, requested_max_output_tokens, output_tokens

    `results` are metric observations, each {"provider", "model", "metric",
    "value"} with the unit METRICS[metric][1]. All timings start just before
    `stream()` is called; only text items (str) count as stream output:

    - ttft: until the first text item of any content (unchanged since Step 001).
    - total_latency: until the stream is fully consumed.
    - output_chunks_per_s: output throughput after the first chunk, where a chunk
      is one non-empty text item (not a provider/API token):

          (non-empty chunks - 1) / (time of last non-empty chunk - time of first)

      Omitted when undefined: fewer than 2 non-empty chunks, or no time elapsed
      between the first and last chunk.

    Raises RuntimeError if the stream has no text, does not report usage exactly
    once, or reports more output tokens than requested.
    """
    request_started = time.perf_counter()
    first_item_at = None
    first_chunk_at = last_chunk_at = None
    chunks = 0
    usage = None
    for item in provider.stream(prompt, max_output_tokens):
        now = time.perf_counter()
        if isinstance(item, Usage):
            if usage is not None:
                raise RuntimeError(f"Provider {provider.name!r} reported usage more than once.")
            usage = item
            continue
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
    if usage is None:
        raise RuntimeError(f"Provider {provider.name!r} did not report token usage.")
    if usage.output_tokens > max_output_tokens:
        raise RuntimeError(
            f"Provider {provider.name!r} reported {usage.output_tokens} output tokens, "
            f"more than the requested maximum of {max_output_tokens}."
        )

    request = {
        "provider": provider.name,
        "model": provider.model,
        "input_tokens": usage.input_tokens,
        "requested_max_output_tokens": max_output_tokens,
        "output_tokens": usage.output_tokens,
    }

    def result(metric: str, value: float) -> dict:
        return {"provider": provider.name, "model": provider.model, "metric": metric, "value": value}

    results = [
        result("total_latency", (stream_finished - request_started) * 1000),
        result("ttft", (first_item_at - request_started) * 1000),
    ]
    if chunks >= 2 and last_chunk_at > first_chunk_at:
        results.append(result("output_chunks_per_s", (chunks - 1) / (last_chunk_at - first_chunk_at)))
    return request, results
