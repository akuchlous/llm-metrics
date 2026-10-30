# Step 001 — TTFT with a dummy provider

## Lead engineer: Where exactly should the TTFT timer start and stop, and what does that boundary include?

**Sample answer:** Start a `time.perf_counter()` timer immediately before calling `provider.stream(prompt)` and stop it when the first token is yielded. `perf_counter` is monotonic, so wall-clock adjustments can't produce negative or jumping durations. Because the dummy's delay runs inside the generator body, the timer has to cover the first `next()`, not only the `stream()` call.

- **Good:** Names the right clock and why. Catches the generator subtlety: calling a generator function runs no code, so timing only `stream()` would measure about 0 ms.
- **Weak:** Doesn't say what the boundary will include for a real HTTP provider: DNS, TCP/TLS handshake, request upload, server queueing, and client-side parsing. Doesn't distinguish a cold connection from a warm one. Those can differ by hundreds of milliseconds and change what "TTFT" means.
- **Improve:** Define the boundary as a written methodology ("from just before the request is issued to the first content token decoded on the client"). State whether connections are reused, and plan to record cold and warm runs separately. Also say what counts as the "first token": the first SSE event, or the first non-empty content delta. Role-only or empty deltas would otherwise understate TTFT.

## Principal engineer: Is `LLMProvider.stream(prompt) -> Iterator[str]` the right abstraction? How would you know it's wrong?

**Sample answer:** It's deliberately minimal. Every real provider can stream text, so it fits them all and avoids speculative design. We'll extend it when we add a real provider.

- **Good:** Resists premature abstraction, and ties change to a concrete trigger.
- **Weak:** "It fits them all" is asserted, not shown. An iterator of strings loses things a benchmark will need: token usage, finish reason, errors mid-stream, server-side timing headers, request IDs. It is also synchronous, which constrains concurrent load testing later.
- **Improve:** Keep it minimal, but name the evidence that would break it: the first real provider integration, or the first concurrency requirement. Name the likely evolution, such as yielding small event objects instead of strings. Contract tests that every provider must pass let the interface change safely.

## Senior manager: The team is told to build in "extremely small steps". How do you stop that becoming slow, or becoming overbuilding by stealth?

**Sample answer:** Each step has a written prompt with explicit out-of-scope items, a status file, and a review gate. Small steps keep reviews easy and stop people adding features nobody asked for.

- **Good:** Identifies the real controls: written scope, an explicit "do not build" list, and a review gate.
- **Weak:** Only addresses overbuilding, not throughput. No measure of whether steps deliver user-visible value, and no time budget, so tiny steps could go on indefinitely.
- **Improve:** Pair small steps with a visible milestone ("a first real TTFT measurement by step N") and time-box each step. Track lead time per step, and periodically check whether the step size still makes sense once the foundations are in place.

## Director: Why invest in a tool that, today, only measures a fake provider? What's the risk?

**Sample answer:** The dummy provider lets us build and test the measurement pipeline safely, without API costs or credentials. Production mode refuses to run, so fake numbers can't be reported as real.

- **Good:** Clear on cost and safety benefits, and on the key guard (no dummy data in `prod`).
- **Weak:** Doesn't connect it to the business goal (independent, credible provider benchmarks). Doesn't name the biggest strategic risk: credibility. One leaked simulated chart that looks real could damage trust in the whole project.
- **Improve:** Frame the dummy phase as de-risking methodology and plumbing before spending on real API calls. Commit to a data-provenance policy: every number carries its environment and source. Set an explicit date or milestone for the first real measurement.
