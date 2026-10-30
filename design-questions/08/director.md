# Step 08 — Director

**Step context:** Step 008 measured total response latency (`total_latency`) alongside TTFT from one streamed request, saved both as separate rows in one transaction, and added a TTFT / Total latency selector to the time-window dashboard.

**Question:** How should TTFT and total latency be used together when comparing or routing between LLM providers, and what does this step still not let you conclude?

## Answer

They answer different product questions:

- **TTFT is responsiveness:** how fast the user sees *something*. It dominates perceived quality in chat and streaming UIs.
- **Total latency is completion time:** how long until the answer is complete and usable. It dominates batch jobs, agents and tool chains, and any flow that waits for the whole response before acting.

A provider can win one and lose the other: fast first token but slow generation, or vice versa. For routing, the choice depends on the use case: interactive traffic should weight TTFT (and its p95), while agents and batch work should weight total latency. Showing both per provider, over the same windows and with the same percentile method, is the minimum for a fair comparison. This step delivers that on simulated data.

What you **cannot** conclude yet:

- **Total latency isn't comparable across different output lengths.** A 50-token answer is faster than a 500-token one regardless of provider. Fair comparison needs throughput (tokens/s), which is the next step, or fixed workloads.
- **Nothing is real yet.** All numbers come from the dummy provider.
- **No cost, quality or error rate,** all of which matter as much as speed for routing.

## Critique

- **Good:** The metric set now separates "starts fast" from "finishes fast", the essential first split for latency-based routing, with consistent windows and percentiles.
- **Weak:** Without output length or workload controls, total latency invites misleading comparisons, and the dashboard doesn't warn about that.
- **Improve:** Before showing total latency for real providers, fix the workload (same prompts and output caps), record output token counts, and add throughput. Present routing recommendations per use case (chat vs. batch), not as a single "fastest provider".
