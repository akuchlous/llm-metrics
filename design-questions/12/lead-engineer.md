# Step 12 — Lead engineer

**Step context:** Step 012 added the first real provider: an OpenAI `gpt-6-luna` adapter on the Responses API using only the standard library, run solely by the explicit `python -m llm_metrics.real_smoke` (one paid call, key from `OPENAI_API_KEY`, stored as `prod`), plus a real-data-only Benchmark API Spend page and clear real-versus-simulated labelling. The price ($0.10 / $0.50 per 1M) is recorded but not yet verified, and the smoke call was not run in the implementation environment.

**Question:** How does the adapter turn OpenAI's server-sent events into our provider contract, and how did you test it without ever touching the network?

## Answer

`OpenAIProvider.stream()` builds one `urllib.request.Request`: a POST to `/v1/responses` with body `{"model", "input", "max_output_tokens": 64, "stream": true, "store": false}`, a bearer key, and `Accept: text/event-stream`. It then reads the response line by line. A tiny SSE parser (`_events`) joins `data:` lines until a blank line and parses the JSON; malformed JSON becomes `ProviderFailure("invalid_response")`.

Translation:

- `response.output_text.delta` → yield the `delta` string, which must be text.
- `response.completed` → yield `Usage` from `response.usage` (non-negative ints only, `bool` rejected), then stop.
- `response.incomplete` because of `max_output_tokens` → still `Usage`, since hitting the cap is expected.
- `response.failed` and `error` → `provider_error`, or `rate_limited` for rate-limit codes.

Opening errors map by HTTP status or exception type. Read-time timeouts and resets map to `timeout` and `transport_error`. Measurement still enforces the cross-provider contract (text present, exactly one final usage, output within the cap).

Testability comes from **dependency injection**: the constructor takes `opener=urllib.request.urlopen`, and tests pass a `FakeOpener` that records the request and returns a `FakeResponse`. That's a `BytesIO` whose `readline` can raise on line N to simulate mid-stream timeouts. A `no_network` decorator patches `socket.socket.connect` and `urlopen` to fail, and the import test runs in a fresh process with sockets disabled.

## Critique

- **Good:** It's small, explicit and table-tested (8 malformed-usage cases, every status family, mid-stream failures). The fake opener checks the exact request body, so the cap and "no tools" are guaranteed. It never makes a network call in tests.
- **Weak:** The event names and shapes come from documentation knowledge, not a live response; the first real call is the real integration test. The parser assumes UTF-8 and line-based reads, and a slow trickle can exceed 60 s in total because the timeout is per socket operation.
- **Improve:** After the first smoke run, capture a sanitized real event stream (with the text removed) as a recorded fixture and replay it in a test. Add an overall attempt deadline. Add a contract-test class every future adapter must pass (stream → chunks + one `Usage`, plus the error mapping table).
