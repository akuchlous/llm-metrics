# Step 08 — Lead engineer

**Step context:** Step 008 measured total response latency (`total_latency`) alongside TTFT from one streamed request, saved both as separate rows in one transaction, and added a TTFT / Total latency selector to the time-window dashboard.

**Question:** How do you measure TTFT and total latency from a single stream, and how do you prove the implementation is correct?

## Answer

`measure_latency()` takes one `perf_counter()` reading before `provider.stream(prompt)`, then iterates the stream once. It records `first_token_received` on the first token (only if it's still `None`), keeps consuming, and takes `stream_finished` after the loop ends. Both results are `(t - request_started) * 1000`, so they share the same start, and `total >= ttft` holds by construction. An empty stream raises before any result exists.

Tests prove the properties that matter, not the implementation:

- **One request:** a `CountingProvider` records `calls == 1` and that all tokens were consumed.
- **TTFT unchanged:** with a 50 ms first-token delay and 30 ms gaps, TTFT stays under 75 ms (it doesn't include the gaps), while total is at least 110 ms.
- **Ordering:** `total >= ttft`, with and without gaps. With a single token, total is about TTFT even when the inter-token delay is 0.5 s, because no wait happens after the last token.
- **Persistence:** the CLI test checks two rows, the same `recorded_at`, and `total_latency >= ttft`.

## Critique

- **Good:** A single, readable loop with no extra abstraction. The tests check the invariants (one call, ordering, unchanged TTFT) rather than mocking time.
- **Weak:** The timing tests rely on `time.sleep` (lower bounds are reliable, upper bounds use generous slack), so the suite is slower and theoretically flaky on a heavily loaded machine. The first-token check runs on every iteration (`is None`), which is trivial cost, but a reader might wonder why it isn't hoisted.
- **Improve:** Inject a fake clock into `measure_latency` to make the timing tests exact and fast, if the sleep-based tests ever flake. Pull the first token out with `next(iter(...))` and then drain the rest, which reads as "first token, then the rest" and makes the empty-stream case explicit.
