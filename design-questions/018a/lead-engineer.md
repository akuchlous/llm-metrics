# Step 018a — Lead engineer

**Step context:** Step 018a inspected the existing OpenAI measurement path and documented its gaps; it changed no production code.

**Question:** How can you tell whether a benchmark is actually capturing first-text latency rather than merely the first streaming event?

## Answer

The audited path is `real_benchmark.run → benchmark.run_attempt → latency.measure_request → OpenAIProvider.stream`. The timer starts just before the HTTP stream opens; TTFT stops at the first `response.output_text.delta` delivered by the provider adapter, not at a metadata event. Total latency uses the same request start but runs through completion. Usage comes from provider completion events, not estimated chunks. The step cited existing tests and two successful live validations, and explicitly classified them as connectivity checks rather than performance samples.

## Critique

- **Good:** The audited timing boundary is explicit, reproducible and aligned with streaming user experience.
- **Weak:** TTFT includes transport/setup delay and does not isolate provider compute.
- **Improve:** On future real runs, record and publish methodology, origin and sample size beside latency distributions; do not present a handful of validations as a ranking.
