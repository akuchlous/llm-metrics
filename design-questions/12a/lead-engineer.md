# Step 12a — Lead engineer

**Step context:** Step 012a closed Step 012 after live validation. It kept the sanitized `--debug` diagnostics, stored OpenAI's `x-request-id` beside each attempt's own UUID (`requests.provider_request_id`, schema version 4), re-verified the gpt-6-luna price against OpenAI's official docs, and confirmed `reasoning.effort: none` from the official model page. An out-of-credit error found during validation is now rejected and not recorded.

**Question:** How does OpenAI's request id get from an HTTP header into the database without changing the generic provider contract?

## Answer

The contract is still "text chunks, then exactly one `Usage`", or a `ProviderFailure`. Both types gained one optional field, `provider_request_id`, defaulting to `None`, so `DummyProvider` and every existing test stay unchanged.

`OpenAIProvider.stream()` reads `x-request-id` once, after the response opens. `_provider_request_id()` keeps it only if it is a short `[A-Za-z0-9_.:-]` token, the same rule as diagnostics, and otherwise returns `None`. It's then attached:

- to the final `Usage` (via `_usage()`);
- to every `ProviderFailure` raised in the stream (via the `failure()` helper);
- to an `invalid_response` raised by the parser (the `except ProviderFailure` block fills it in if missing);
- to HTTP 5xx/429/408/504 failures (read from the error's headers).

`measure_request()` copies it onto the attempt dict from `Usage` or the failure. `save_request()` defaults it to `None`, and schema version 4 adds the nullable column.

## Critique

- **Good:** It's additive, with no new stream item, so TTFT and chunk logic are untouched. Unsafe values become NULL, never a fake marker. Tests cover success, each failure path, and unsafe or missing headers.
- **Weak:** A failure detected by measurement (the stream ended without a final event) loses the id, although the provider saw it. Putting an id on `Usage` slightly widens that type's meaning beyond token counts.
- **Improve:** Raise "stream ended without a final event" inside the provider as `invalid_response`, so the id survives. If more per-request provider metadata appears, such as cached or reasoning tokens, rename `Usage` to a broader final report.
