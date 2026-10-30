# Step 10 — Director

**Step context:** Step 010 added a `requests` table (own UUID identity, provider-reported input/output tokens, requested max output tokens, effective per-1M prices, and unrounded costs) linked to the existing metric observations, a `Usage` event at the end of each stream, a single `pricing.py`, schema version 2, and a `/requests` view of individual calls.

**Question:** Why does an independent LLM benchmark need per-request cost and token accounting, not just latency? And what has to be true before these cost numbers can inform buying or routing decisions?

## Answer

Latency alone can't drive a provider decision. The real question is "fast enough at what price for this workload?". Step 010 makes every request explainable on both axes: total latency (the primary latency), TTFT (streaming feel), chunk throughput, input and output tokens, the cap requested, and the exact cost with the rates used. That supports the public use case of inspecting an individual benchmark call and explaining both its speed and its bill. Because prices are stored per request, historical comparisons remain auditable after providers change prices, which they do often.

Before these numbers can inform decisions:

- **Real token counts from each provider's billing usage,** not a simulated tokenizer. The same prompt tokenizes differently across providers, so token counts aren't comparable across providers, but **cost is**.
- **Real, sourced and dated prices,** with a policy for promotions, tiers, caching discounts and batch pricing (none modelled yet).
- **Fixed, published workloads** (prompts and output caps), so cost-per-request comparisons are like for like.
- **Cost per useful outcome,** eventually: a cheap provider that fails or produces poor answers isn't cheap. That needs error and quality data (out of scope so far).

## Critique

- **Good:** It establishes the right unit of analysis (the request), keeps cost explainable over time, and refuses to claim tokenizer equivalence. That's credible groundwork.
- **Weak:** All of it is simulated today, there's no aggregate cost view (e.g. p50 cost per request, or cost over time), and the per-token price model ignores real pricing complexity (cached input, tiers, batch discounts).
- **Improve:** When the first real provider lands, validate recorded tokens and costs against the provider's billing for a sample of requests. Add an aggregate cost metric to the dashboard. Publish the price sources and the workload definition alongside every cost comparison.
