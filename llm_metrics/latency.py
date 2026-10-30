"""Measurement of one benchmark attempt.

Owns the timer boundaries and the provider-contract checks: one provider call
produces an outcome, token facts, and the metric observations below. It does
not price, store, or print anything (see `benchmark`).

All timings use `time.perf_counter()` (monotonic) and start just before
`provider.stream()` is called, so connection setup, queueing, and prefill are
inside every latency.
"""

import time

from llm_metrics import outcomes
from llm_metrics import providers

# Every metric this module produces: name -> (display label, unit of `value`).
# The metric name fixes the unit; never store a different unit under an
# existing name, because stored observations would silently change meaning.
# Order is display order: total latency is the primary user-facing latency,
# TTFT is a streaming diagnostic, and token throughput is preferred over chunk
# throughput (kept for continuity with older data).
METRICS = {
    "total_latency": ("Total latency", "ms"),
    "ttft": ("TTFT", "ms"),
    "output_tokens_per_s": ("Output token throughput", "tokens/s"),
    "output_chunks_per_s": ("Output chunk throughput", "chunks/s"),
}


class _InvalidResponse(Exception):
    """The stream broke the provider contract (see `LLMProvider.stream`)."""


def measure_request(
    provider: providers.LLMProvider, prompt: str, max_output_tokens: int
) -> tuple[dict, list[dict]]:
    """Makes one benchmark attempt (exactly one provider call) and measures it.

    Metric semantics (all measured from just before `stream()` is called):

    - total_latency (ms): until the stream is fully consumed.
    - ttft (ms): until the first text item of any content, including empty.
    - output_tokens_per_s: `Usage.output_tokens` divided by the time from the
      first to the last non-empty chunk, so TTFT is excluded. The token count is
      the provider's, for the whole response, while the timing is the client's
      view of the stream: this is observed effective generation throughput, not
      the provider's internal decoding speed. Tokens in the first chunk are
      counted but its wait is not, so very short responses read high.
    - output_chunks_per_s: (non-empty chunks - 1) over the same interval. A
      chunk is one non-empty text item, not a token.

    A throughput is omitted (never stored as 0 or infinity) when undefined:
    fewer than 2 non-empty chunks, no elapsed time between them, or (tokens/s
    only) no output tokens reported.

    Args:
        provider: Provider to call once. Not retried.
        prompt: Prompt text; passed through, never stored.
        max_output_tokens: Output cap requested from the provider.

    Returns:
        (attempt, results). `attempt` always has "provider", "model",
        "requested_max_output_tokens", "outcome" (`outcomes.SUCCESS` or a
        failure category), "input_tokens", "output_tokens", "failed_after_ms",
        "provider_request_id", and "cached_input_tokens".

        On success: token facts come from the provider's `Usage` (never from
        chunk counts), "failed_after_ms" is None, and `results` holds the metric
        observations, each {"provider", "model", "metric", "value"} in the unit
        `METRICS[metric][1]`.

        On failure: token counts and cached tokens are None (unknown, not zero),
        `results` is empty (partial timings are discarded so success-only
        distributions stay clean), "failed_after_ms" is the time from request
        start until the failure was detected, and "diagnostics" holds the
        provider's sanitized debug details (never stored).

        A failure is either a `ProviderFailure` raised by the provider (its
        category), or a contract violation detected here, recorded as
        "invalid_response": no text, usage missing or repeated, text after
        usage, or more output tokens than requested.

    Raises:
        Exception: Any other exception is an llm-metrics bug, not a provider
            outcome, and propagates unrecorded.
    """
    request_started = time.perf_counter()
    first_item_at = None
    first_chunk_at = last_chunk_at = None
    chunks = 0
    usage = None
    try:
        for item in provider.stream(prompt, max_output_tokens):
            now = time.perf_counter()
            if isinstance(item, providers.Usage):
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
    except (providers.ProviderFailure, _InvalidResponse) as failure:
        failed_at = time.perf_counter()
        if isinstance(failure, providers.ProviderFailure):
            outcome = failure.category
            provider_request_id = failure.provider_request_id
        else:
            outcome = "invalid_response"
            # The provider may have identified the request before the contract
            # violation was detected here (e.g. output above the cap).
            provider_request_id = (
                usage.provider_request_id if usage is not None else None
            )
        attempt = {
            "provider": provider.name,
            "model": provider.model,
            "requested_max_output_tokens": max_output_tokens,
            "outcome": outcome,
            "input_tokens": None,
            "output_tokens": None,
            "failed_after_ms": (failed_at - request_started) * 1000,
            "provider_request_id": provider_request_id,
            "cached_input_tokens": None,
            # Not a storage column: printed by `real_smoke --debug` only.
            "diagnostics": getattr(failure, "diagnostics", {}),
        }
        return attempt, []

    attempt = {
        "provider": provider.name,
        "model": provider.model,
        "requested_max_output_tokens": max_output_tokens,
        "outcome": outcomes.SUCCESS,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "failed_after_ms": None,
        "provider_request_id": usage.provider_request_id,
        "cached_input_tokens": usage.cached_input_tokens,
    }

    def observation(metric: str, value: float) -> dict:
        return {
            "provider": provider.name,
            "model": provider.model,
            "metric": metric,
            "value": value,
        }

    results = [
        observation(
            "total_latency", (stream_finished - request_started) * 1000
        ),
        observation("ttft", (first_item_at - request_started) * 1000),
    ]
    if chunks >= 2 and last_chunk_at > first_chunk_at:
        generation_s = last_chunk_at - first_chunk_at
        if usage.output_tokens >= 1:
            # Zero reported tokens alongside visible text is contradictory, so
            # no rate is recorded rather than a fabricated 0 tokens/s.
            results.append(
                observation(
                    "output_tokens_per_s", usage.output_tokens / generation_s
                )
            )
        results.append(
            observation("output_chunks_per_s", (chunks - 1) / generation_s)
        )
    return attempt, results
