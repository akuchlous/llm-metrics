"""Measurement of one benchmark attempt: outcome, token facts, total latency,
TTFT, and output chunk throughput."""

import time

from llm_metrics.outcomes import SUCCESS
from llm_metrics.providers import LLMProvider, ProviderFailure, Usage

# Every metric this module produces: name -> (display label, unit of `value`).
# The metric name fixes the unit; never store a different unit under a name.
# Total latency is listed first: it is the primary user-facing latency; TTFT is
# diagnostic (streaming responsiveness).
METRICS = {
    "total_latency": ("Total latency", "ms"),
    "ttft": ("TTFT", "ms"),
    "output_chunks_per_s": ("Output throughput", "chunks/s"),
}


class _InvalidResponse(Exception):
    """The stream broke the provider contract (see LLMProvider)."""


def measure_request(
    provider: LLMProvider, prompt: str, max_output_tokens: int
) -> tuple[dict, list[dict]]:
    """Make one benchmark attempt (one provider call); return (attempt, results).

    `attempt` always has: provider, model, requested_max_output_tokens, outcome
    ("success" or a failure category from outcomes.FAILURE_CATEGORIES),
    input_tokens, output_tokens, failed_after_ms.

    On success: input_tokens/output_tokens come from the provider's final
    `Usage` (never from chunk counts), failed_after_ms is None, and `results`
    holds the metric observations, each {"provider", "model", "metric", "value"}
    with the unit METRICS[metric][1]. All timings start just before `stream()`:

    - total_latency: until the stream is fully consumed.
    - ttft: until the first text item of any content (unchanged since Step 001).
    - output_chunks_per_s: (non-empty chunks - 1) / (time of last non-empty
      chunk - time of first); a chunk is one non-empty text item, not a token.
      Omitted when undefined (fewer than 2 non-empty chunks, or no elapsed time).

    On failure: token counts are None (unknown, not zero), `results` is empty
    (partial timings are discarded, so success-only distributions stay clean),
    and failed_after_ms is the time from request start until the failure was
    detected. Failures are a ProviderFailure raised by the provider (its
    category), or a contract violation detected here ("invalid_response"): no
    text, usage missing or repeated, text after usage, or more output tokens
    than requested. Any other exception is a bug and propagates.
    """
    request_started = time.perf_counter()
    first_item_at = None
    first_chunk_at = last_chunk_at = None
    chunks = 0
    usage = None
    try:
        for item in provider.stream(prompt, max_output_tokens):
            now = time.perf_counter()
            if isinstance(item, Usage):
                if usage is not None:
                    raise _InvalidResponse("usage reported more than once")
                usage = item
                continue
            if usage is not None:
                raise _InvalidResponse("text after usage")
            if first_item_at is None:
                first_item_at = now
            if item:
                chunks += 1
                if first_chunk_at is None:
                    first_chunk_at = now
                last_chunk_at = now
        stream_finished = time.perf_counter()
        if first_item_at is None:
            raise _InvalidResponse("no text")
        if usage is None:
            raise _InvalidResponse("no usage reported")
        if usage.output_tokens > max_output_tokens:
            raise _InvalidResponse("more output tokens than requested")
    except (ProviderFailure, _InvalidResponse) as failure:
        failed_at = time.perf_counter()
        outcome = failure.category if isinstance(failure, ProviderFailure) else "invalid_response"
        attempt = {
            "provider": provider.name,
            "model": provider.model,
            "requested_max_output_tokens": max_output_tokens,
            "outcome": outcome,
            "input_tokens": None,
            "output_tokens": None,
            "failed_after_ms": (failed_at - request_started) * 1000,
        }
        return attempt, []

    attempt = {
        "provider": provider.name,
        "model": provider.model,
        "requested_max_output_tokens": max_output_tokens,
        "outcome": SUCCESS,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "failed_after_ms": None,
    }

    def result(metric: str, value: float) -> dict:
        return {"provider": provider.name, "model": provider.model, "metric": metric, "value": value}

    results = [
        result("total_latency", (stream_finished - request_started) * 1000),
        result("ttft", (first_item_at - request_started) * 1000),
    ]
    if chunks >= 2 and last_chunk_at > first_chunk_at:
        results.append(result("output_chunks_per_s", (chunks - 1) / (last_chunk_at - first_chunk_at)))
    return attempt, results
