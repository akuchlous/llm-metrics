# Step 01 — Lead engineer

**Question:** Where exactly should the TTFT timer start and stop, and what does that boundary include?

## Answer

The timer starts with `time.perf_counter()` immediately before `provider.stream(prompt)` is called, and stops when the first token is yielded (`ttft.py`). `perf_counter` is monotonic and high-resolution, so NTP or wall-clock adjustments can't produce negative or jumping durations.

There is one subtlety: `stream()` is a generator, so calling it runs no code. The dummy provider's delay happens on the first `next()`, so the timed region must include the first iteration. Timing only the call would report about 0 ms. The loop `break`s at the first token, because draining the stream isn't part of TTFT.

For a real HTTP provider, this boundary will include everything the client experiences before the first token: DNS lookup, TCP/TLS handshake (on a cold connection), request upload, provider queueing and prefill, and client-side parsing of the first event. That is deliberate, because TTFT is a user-perceived metric.

## Critique

- **Good:** Correct clock. Catches the generator pitfall. Measures what a user feels, not an internal server number. Empty streams raise an error instead of reporting a fake value.
- **Weak:** The boundary is only described in code and a decision note; there's no methodology document. "First token" isn't yet defined for real APIs: providers often send role-only or empty first events, and counting those would understate TTFT. Cold and warm connections aren't distinguished, and they can differ by hundreds of milliseconds.
- **Improve:** Write a short methodology section: "first non-empty content delta, measured on the client". Record whether the connection was reused, and report cold and warm runs separately. Add a test with a provider whose first event is empty.
