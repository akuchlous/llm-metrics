# Step 11 — Lead engineer

**Step context:** Step 011 persisted every benchmark attempt with an outcome (`success` or a stable failure category: timeout, rate_limited, provider_error, transport_error, invalid_response), stored unknown token/cost facts as NULL with a `failed_after_ms` field, kept failed attempts out of latency/throughput observations, added an "observed benchmark success rate" with failures by category, and upgraded the schema to version 3 by rebuilding `requests`.

**Question:** Walk through how `measure_request` turns one stream into either a success or a classified failure. What exactly is caught, and why not catch everything?

## Answer

The whole stream loop and its post-checks run inside one `try`:

- **The provider** raises `ProviderFailure(category)`. The category is validated in its constructor, so an adapter can't invent `"http_503"`.
- **The measurement** raises a private `_InvalidResponse` for contract violations: a second `Usage`, text after `Usage`, no text at all, no usage, or `output_tokens > max_output_tokens`.
- **`except (ProviderFailure, _InvalidResponse)`** records `failed_after_ms` (request start until the failure was caught) and returns an attempt with `outcome` set to the category (or `invalid_response`), `input_tokens` and `output_tokens` as `None`, and **no results**. Partial TTFT and chunks are dropped.
- **Success** builds the attempt from `Usage` and returns the three metric results, unchanged since Step 010.

Not catching everything is deliberate. A `KeyError` or `TypeError` inside llm-metrics is a bug in *our* code; recording it as a provider failure would blame the provider and corrupt the success rate. A test (`Buggy` provider raising `KeyError`) proves it propagates. Messages are never stored: the CLI prints only the category, and a test checks that the provider's message text doesn't appear.

## Critique

- **Good:** Narrow, intentional exception handling. A clear split between provider-reported and contract-detected failures. Deterministic tests for every category, both before and after some text has streamed.
- **Weak:** Real adapters must remember to wrap *all* their native exceptions (e.g. `socket.timeout`, `json.JSONDecodeError`) into `ProviderFailure`. Any they miss will crash the run instead of being recorded. There's no measurement-level deadline, so a stream that hangs without raising blocks forever.
- **Improve:** Give adapters a small, tested helper or contract-test suite (e.g. "a raised `OSError` must surface as `transport_error`"). Add an overall attempt deadline in `measure_request` (a monotonic check between items) that yields `timeout` even if the adapter's own timeouts fail.
