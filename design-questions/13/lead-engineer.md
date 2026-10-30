# Step 13 — Lead engineer

**Step context:** Step 013 completed the Metrics v1 request data model. It added `output_tokens_per_s` (provider-reported output tokens over the first-to-last output chunk interval), a required `workload_id` naming the benchmark case, and `origin_cloud` / `origin_region` for where the runner executed (configured by environment variables, default `local` / `unknown`). It also added cache facts: the requested `cache_policy` (the OpenAI smoke request sends explicit cache mode with no breakpoints and records `disabled`; the simulated provider records `provider_default`) and provider-reported `cached_input_tokens` (0 = reported zero, NULL = not reported). Schema versions 5 and 6 add these as request columns; historical rows stay NULL, with cache policy `unknown`.

**Question:** Walk through how `output_tokens_per_s` is computed, and why it can never be zero or infinite.

## Answer

`measure_request()` already timed the first and last non-empty text chunks for `output_chunks_per_s` (Step 009). Step 013 reuses that interval. After the stream completes with exactly one `Usage`:

```python
if chunks >= 2 and last_chunk_at > first_chunk_at:
    generation_s = last_chunk_at - first_chunk_at  # TTFT excluded
    if usage.output_tokens >= 1:
        results.append(result("output_tokens_per_s", usage.output_tokens / generation_s))
    results.append(result("output_chunks_per_s", (chunks - 1) / generation_s))
```

- **No infinity:** the denominator is positive by the guard.
- **No zero:** a zero-token count is omitted, never stored as 0.
- **No chunk counting:** the numerator is the provider's `Usage.output_tokens`, never `chunks`.
- **Failures:** they return before this point, so they never add a throughput value.

Tests pin it with a mocked `perf_counter`. One case has 3 chunks but 40 reported tokens, a 1 s TTFT and a 0.4 s stream tail. Tokens/s comes out at exactly 40 / 0.2 = 200, and chunks/s at 10, as before.

## Critique

- **Good:** It's one shared interval and a few lines. Undefined cases are omitted, matching the existing "unknown is not zero" rule. The tests isolate each edge.
- **Weak:** The numerator includes tokens that arrived in the first chunk, but the interval starts after them, so short responses read high. OpenAI's count also includes reasoning tokens produced before the first text.
- **Improve:** Once providers report per-chunk token counts or reasoning tokens separately, subtract the first chunk's tokens and the reasoning tokens. Until then, show `n` and the output-token size beside the percentiles so low-token samples are visible.
