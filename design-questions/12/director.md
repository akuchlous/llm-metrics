# Step 12 — Director

**Step context:** Step 012 added the first real provider: an OpenAI `gpt-6-luna` adapter on the Responses API using only the standard library, run solely by the explicit `python -m llm_metrics.real_smoke` (one paid call, key from `OPENAI_API_KEY`, stored as `prod`), plus a real-data-only Benchmark API Spend page and clear real-versus-simulated labelling. The price ($0.10 / $0.50 per 1M) is recorded but not yet verified, and the smoke call was not run in the implementation environment.

**Question:** Why publish what llm-metrics itself spends on benchmarking, and what must be true before those numbers appear publicly (e.g. on llmxchange.com)?

## Answer

An independent benchmark is a business with its own unit economics. Publishing our own API spend does three things:

1. **It builds trust.** Readers see the sample sizes and costs behind every claim (how many paid calls produced this p95?), which is hard for a vendor-funded benchmark to fake.
2. **It informs strategy.** Spend per provider and model per window tells us what a given benchmark cadence costs, which drives how many models, how often, and with what workloads we can afford to run.
3. **It makes model costs concrete.** Per-request cost with stored rates answers "what does one realistic request cost on model X?", separately from list prices.

The page states what it is and isn't: the API token cost of llm-metrics' own benchmark requests, not provider revenue, not every user's cost, not infrastructure cost, and not a normalized price comparison. That boundary protects credibility.

Before publishing:

- **Verified prices** with a date and source (currently flagged unverified), and reconciliation against the provider's invoice.
- **Real runs:** at least the first smoke run, then a defined workload and cadence (out of scope until a scheduler step).
- **A total-cost view** that eventually includes hosting and infrastructure, clearly labelled, if we want to claim the full "cost to run the benchmark".
- **Failure accounting stated:** failed calls may be billed but are shown as unknown.

## Critique

- **Good:** Transparency is designed in from the first real call: the costs are explainable, the populations separated, and the wording careful.
- **Weak:** With a single model and no cadence, the published numbers would be anecdotal. "Unknown cost of failures" may confuse non-technical readers. Infrastructure cost is absent, so "cost to run llm-metrics" is incomplete.
- **Improve:** Publish only once a scheduled, documented workload exists. Show spend with call counts and the pricing date beside every figure. Add an infrastructure-cost line item, maintained manually, before calling it the total operating cost.
