# Step 17 — Lead engineer

**Step context:** Step 017 was a behavior-preserving cleanup. LiteLLM was evaluated against the Step 016 measurement contract and not adopted: it fetches a price map over the network on import, records zero usage when a provider reports none, sends Gemini and xAI to different endpoints than the request profiles name, and had compromised PyPI releases in March 2026. Duplicated adapter behavior moved into `http_streaming` (`status_failure`, `checked_usage`, `StreamContext`), `real_smoke` now delegates to `real_benchmark.run`, and test fakes are shared. SQLAlchemy Core + Alembic are recommended for the Google Cloud persistence step. Package code shrank by about 150 lines, with no change to wire requests, stored facts, pages or the API.

**Question:** Four adapters had the same `try/except` and closure code. How did you decide what to share and what to leave duplicated?

## Answer

I shared only behavior that is identical by definition, not by appearance:

- **Status mapping** (`status_failure`). 429, 408/504 and 5xx mean the same thing to every provider for our outcome vocabulary. Provider-specific account errors are checked by each adapter first.
- **Failure identification** (`StreamContext`). Every failure raised while a response is open must carry that response's status and request id. Only the source of the id differs (header vs stream), so the context takes it either way through `set_request_id`.
- **Usage validation** (`checked_usage`). "Counts are non-negative ints; cached ≤ input; None stays None" is our invariant, not a provider's.

Left duplicated: event dispatch, usage field names, error-code tables and request bodies. Those are each provider's contract. Merging OpenAI and xAI's similar Responses parsers would let one provider's change silently alter the other.

## Critique

- **Good:** Each helper has one current responsibility and named callers. The per-adapter files now read as "this provider's protocol".
- **Weak:** `StreamContext` is mutable (the request id is learned mid-stream), so its correctness depends on adapters calling `set_request_id` before raising.
- **Improve:** Add a test per adapter that a failure after the id event carries the id. Today that is covered for some providers only.
