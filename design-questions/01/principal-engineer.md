# Step 01 — Principal engineer

**Question:** Is `LLMProvider.stream(prompt) -> Iterator[str]` the right abstraction? How would you know it's wrong?

## Answer

It's the right abstraction for Step 001 because it encodes exactly one fact we're sure of: every provider we care about can stream text in response to a prompt, and streaming is required to observe the first token. Plus `name` and `model` for labelling results. Anything more (options, async, metadata) would be guessing.

It becomes wrong when real requirements arrive, and we can predict which ones:

1. **Metadata.** Token counts, finish reason, request IDs and server timing don't fit in `str`, so the stream will need small event objects.
2. **Errors mid-stream.** A benchmark must record partial failures, not just raise.
3. **Concurrency.** Load tests want `async` or threads; a synchronous iterator limits that.

The signal is the first real provider integration: if the adapter has to smuggle data out of band, the interface is wrong.

## Critique

- **Good:** Truly minimal, easy to implement for a fake, and it kept Steps 001–006 simple. It hasn't needed to change in six steps, which suggests the scope was right.
- **Weak:** There are no contract tests that any provider must pass, so a future real provider could subtly violate expectations (for example, yielding empty strings) without a test noticing. `name` and `model` are class attributes, which assumes one model per provider class.
- **Improve:** Add a small provider contract test suite now. It's cheap and protects the boundary. When the interface evolves, change it in one deliberate step that updates the dummy and the first real provider together, rather than drifting.
