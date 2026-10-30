# Step 12a — Principal engineer

**Step context:** Step 012a closed Step 012 after live validation. It kept the sanitized `--debug` diagnostics, stored OpenAI's `x-request-id` beside each attempt's own UUID (`requests.provider_request_id`, schema version 4), re-verified the gpt-6-luna price against OpenAI's official docs, and confirmed `reasoning.effort: none` from the official model page. An out-of-credit error found during validation is now rejected and not recorded.

**Question:** Why is the provider's request id a nullable attribute and not part of the request's identity, and which id did you choose?

## Answer

Identity must exist for every attempt, under our control, before any network call. The provider id fails all three:

- a connection failure or a simulated run has none;
- a provider can change its format;
- a second provider may not offer one.

So `requests.id` (our UUID, D036) stays the key, and `provider_request_id` is diagnostic metadata (D048): no uniqueness constraint, no index, no joins. The relationship is one-to-zero-or-one: our request ↔ the provider's request.

I chose `x-request-id` over the response object's `resp_…` id:

- It arrives with HTTP errors too, before any event is parsed.
- It's what OpenAI support asks for.
- With `store: false`, a response id can't be retrieved later anyway.

The schema change is one `ALTER TABLE ADD COLUMN`, needing no table rebuild; old rows get NULL and are not backfilled.

## Critique

- **Good:** It's the minimum that meets the need: no tracing service, no generic abstraction, and our identity is unchanged. The upgrade is cheap and tested against the exact Step-011 schema.
- **Weak:** Nothing enforces a format or provider scope. A future provider whose ids collide with OpenAI's would need the `provider` column to tell them apart, which works but isn't stated in the schema.
- **Improve:** When a second provider arrives, document each provider's id source in its adapter, and consider `CHECK (length(provider_request_id) <= 100)` to match the sanitizer.
