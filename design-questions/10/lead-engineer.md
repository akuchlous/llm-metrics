# Step 10 — Lead engineer

**Step context:** Step 010 added a `requests` table (own UUID identity, provider-reported input/output tokens, requested max output tokens, effective per-1M prices, and unrounded costs) linked to the existing metric observations, a `Usage` event at the end of each stream, a single `pricing.py`, schema version 2, and a `/requests` view of individual calls.

**Question:** How do token counts flow from the provider into storage, and how do you guarantee they are never derived from stream chunks?

## Answer

`provider.stream(prompt, max_output_tokens)` yields text chunks (`str`) followed by exactly one `Usage(input_tokens, output_tokens)`. `measure_request` iterates once: `str` items drive TTFT and chunk throughput, and the `Usage` item is captured separately. It never influences timing or chunk counts. After the loop it validates:

- `usage is None` → "did not report token usage";
- a second `Usage` → "reported usage more than once";
- `output_tokens > max_output_tokens` → it exceeded the requested maximum.

It then returns `request = {provider, model, input_tokens, requested_max_output_tokens, output_tokens}`, built only from `Usage` and the argument. The CLI adds prices and costs, and `save_request` writes the request row and its linked observations in one transaction.

The guarantee is structural (there is no code path from `chunks` to a token field) and tested. The dummy streams 5 chunks but reports 7 tokens, a test asserts `output_tokens != 5`, a provider test shows one 12-character chunk is 3 tokens, and scripted providers check the missing, duplicate and over-cap cases.

## Critique

- **Good:** A single pass, explicit validation, and tests that specifically guard the chunks-versus-tokens distinction the prompt cared about.
- **Weak:** `stream()` now yields mixed types (`str | Usage`), so every consumer must remember `isinstance` checks, and a provider that yields `Usage` *before* text isn't rejected (it's accepted silently). The dummy provider's tokenizer is reused for both prompt and output, so a bug in it would affect both counts the same way and could hide in tests.
- **Improve:** Enforce "`Usage` must be last" (reject text after usage) and add a test for it. Consider a tiny `StreamEvent` type, or a separate final-usage channel, if a second provider makes the mixed stream awkward. Add an independent hand-computed expectation (e.g. a 25-character output gives 7) in the tests rather than calling `simulated_token_count` on both sides; the current tests already use literals.
