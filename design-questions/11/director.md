# Step 11 — Director

**Step context:** Step 011 persisted every benchmark attempt with an outcome (`success` or a stable failure category: timeout, rate_limited, provider_error, transport_error, invalid_response), stored unknown token/cost facts as NULL with a `failed_after_ms` field, kept failed attempts out of latency/throughput observations, added an "observed benchmark success rate" with failures by category, and upgraded the schema to version 3 by rebuilding `requests`.

**Question:** Why does reliability belong in an LLM benchmark alongside speed and cost, and how does this step change what a provider comparison can honestly say?

## Answer

Benchmarks that record only successful calls are biased in the provider's favour. A provider that is very fast when it succeeds but fails 20% of the time would look as good as, or better than, one that always answers. For users and buyers, a failed call has real costs: retries add latency, fallbacks add complexity, and rate limits cap throughput. Step 011 makes every attempt count. The success rate uses all attempts, failures are classified into stable cross-provider categories, and successful performance and cost stay clean and separate. A comparison can now say "p95 total latency X ms *and* observed success rate Y% over N attempts, with Z% rate-limited" for the same window and conditions.

Strategically, the stable categories matter more than the dashboard. They let a future OpenAI, Anthropic or Google adapter map native errors into one vocabulary, so cross-provider reliability comparisons don't depend on each vendor's error wording. Keeping retries out of scope avoids hiding failures inside "eventual success" before we've decided how to report them.

## Critique

- **Good:** It eliminates survivorship bias, keeps definitions precise ("observed", not uptime), and creates the vocabulary needed for multi-provider reliability comparisons.
- **Weak:** Everything is still simulated. The meaning of categories across real providers (e.g. is an overloaded 529 a rate limit or a provider error?) is unresolved. There's no notion of retries or of a "logical request" success rate, which is often what customers actually experience.
- **Improve:** Before publishing reliability numbers, document the per-provider error-to-category mapping and have it reviewed. Decide how retries are reported: separate attempts plus a logical-request success rate. Pair success rate with sample size and measurement origin in every public comparison.
