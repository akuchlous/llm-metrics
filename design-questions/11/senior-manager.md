# Step 11 — Senior manager

**Step context:** Step 011 persisted every benchmark attempt with an outcome (`success` or a stable failure category: timeout, rate_limited, provider_error, transport_error, invalid_response), stored unknown token/cost facts as NULL with a `failed_after_ms` field, kept failed attempts out of latency/throughput observations, added an "observed benchmark success rate" with failures by category, and upgraded the schema to version 3 by rebuilding `requests`.

**Question:** A dashboard now shows a "success rate". How do you make sure people interpret it correctly and don't treat it as an SLA or as provider uptime?

## Answer

The wording and the scope are built into the product:

- **The name is precise:** "Observed benchmark success rate (window)", plus the sentence "All benchmark attempts made by this runner in the window, successful or not. This is what our runner observed, not the provider's overall uptime."
- **The sample size is always shown** ("1 of 4 attempts succeeded"). With no attempts there is **no rate** ("so no success rate") rather than a misleading 0% or 100%.
- **Failures are broken down by category,** so a 25% rate is explained (rate limiting is a capacity or quota conversation; provider errors and timeouts are reliability conversations).
- **Separate populations:** latency and throughput below are labelled "(successful attempts only)", so nobody assumes failures are inside the percentiles.
- **Definitions are written down:** decision D042 (population, formulas, no-attempts behaviour), and the step report.

## Critique

- **Good:** Honest naming, a visible sample size, no false precision on empty data, and an actionable breakdown. These are the main guards against misreading.
- **Weak:** With very few attempts, a percentage is still shown (e.g. "25.0%" from 4 attempts) with no confidence interval or minimum sample size, which invites over-reaction. Our runner's own problems (local network, laptop sleep) are indistinguishable from provider failures, which is especially relevant for `transport_error`.
- **Improve:**
  - Hide or grey out the rate below a minimum attempt count, or show a simple confidence interval.
  - Record where the runner ran (future origin/region dimension) so runner-side failures can be separated.
  - Agree with stakeholders, in writing, that this metric isn't an SLA before it appears in any external report.
