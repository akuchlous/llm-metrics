# Step 12 — Principal engineer

**Step context:** Step 012 added the first real provider: an OpenAI `gpt-6-luna` adapter on the Responses API using only the standard library, run solely by the explicit `python -m llm_metrics.real_smoke` (one paid call, key from `OPENAI_API_KEY`, stored as `prod`), plus a real-data-only Benchmark API Spend page and clear real-versus-simulated labelling. Follow-up: the owner verified the price ($0.10 / $0.50 per 1M); the first live call failed as `provider_error`, so sanitized `--debug` diagnostics and `reasoning.effort: none` were added.

**Question:** You crossed the simulated-to-real boundary. Which design decisions protect measurement integrity, and where is it most likely to break first with real traffic?

## Answer

The decisions that protect integrity:

1. **One attempt = one HTTP request.** We don't use the SDK, so there are no hidden default retries; `stream()` makes exactly one `urlopen` call (tested).
2. **Authoritative usage only.** Token counts come from `response.usage`, never from chunks or the dummy tokenizer. Anything malformed is `invalid_response`, never a guess.
3. **Classification at the boundary,** with a deliberate exclusion: 400/401/403/404 raise `RequestRejected` and aren't recorded, because a bad key isn't provider unreliability. 429, 5xx, timeouts and transport errors *are* recorded.
4. **Population separation.** Real rows are `prod` and simulated rows `test`. Every page shows exactly one population, with a distinct label, and spend reads `prod` only.
5. **Explainable cost.** Rates are stored per request, and provenance (source, verification date) lives next to the price. The unverified state is explicit in code, in CLI output and in the docs.

Where it will break first:

- **Reasoning-token behaviour.** If `gpt-6-luna` reasons before answering, a 64-token cap can be consumed invisibly: no text arrives, and the attempt becomes `invalid_response`. Output tokens (and cost) then include reasoning that TTFT and chunk throughput don't see.
- **Event-schema drift.** A renamed event or a moved `usage` field turns every attempt into `invalid_response`. That's safe (no fabricated numbers) but it zeroes the success rate.
- **Network-path noise.** `transport_error` mixes our laptop's connectivity with the provider's, and there's no origin dimension yet.

## Critique

- **Good:** Integrity was prioritised over convenience (no SDK retries, no inference, honest unknowns, explicit unverified prices), and the boundary stayed generic: no interface change was needed.
- **Weak:** Nothing has met reality yet: the price and event format are unverified, and no real call has run. "Unverified" is surfaced but not *enforced*; a publish path could still show unverified costs.
- **Improve:** Make verification a gate: refuse to show cost on the public spend page (or flag it prominently) while `PRICE_PROVENANCE` is `None`. Record `output_tokens_details.reasoning_tokens` once its semantics are confirmed. Add an origin/runner identifier before benchmarks run anywhere other than one laptop.
