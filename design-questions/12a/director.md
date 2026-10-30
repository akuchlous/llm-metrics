# Step 12a — Director

**Step context:** Step 012a closed Step 012 after live validation. It kept the sanitized `--debug` diagnostics, stored OpenAI's `x-request-id` beside each attempt's own UUID (`requests.provider_request_id`, schema version 4), re-verified the gpt-6-luna price against OpenAI's official docs, and confirmed `reasoning.effort: none` from the official model page. An out-of-credit error found during validation is now rejected and not recorded.

**Question:** The project has a $10/day operating budget. Why doesn't this step enforce it, and what has to be true before scheduled real benchmarks start?

## Answer

Today a paid call happens only when a person runs `python -m llm_metrics.real_smoke`, one call capped at 64 output tokens, about $0.00001. Spend is bounded by human action. A local hard cap would protect nothing real: it couldn't see hosting costs, and it would add code that the hosted design would replace.

The budget is recorded in the direction log as a constraint for the deployment/scheduling step. Before scheduled runs start, we need:

- a spend guardrail that counts both API and infrastructure cost, and fails closed;
- verified per-model prices with provenance (now in place for gpt-6-luna);
- a confirmed classification that keeps our own account problems out of provider reliability (now in place);
- per-request traceability to the provider (now in place);
- a defined benchmark methodology, including reasoning effort per workload. This one is still open.

## Critique

- **Good:** It doesn't build a fake control. The prerequisites that are cheap to do now (price provenance, classification, traceability) were done while the context was fresh.
- **Weak:** $10/day is an aggregate constraint without a model yet: how many calls per model per day, and how much is reserved for hosting. Out-of-credit was found by failure, not by monitoring.
- **Improve:** Write the budget allocation (API versus hosting, per provider) as part of the scheduling step's design. Add a provider-balance or spend check before any automated run.
