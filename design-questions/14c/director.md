# Step 14c — Director

**Step context:** Step 014c split the dashboard's data interpretation from its presentation. New `llm_metrics/analytics.py` returns natural values (floats, ints, aware datetimes, None for unknown) for metric windows (successful observations with a nearest-rank summary, plus the success rate over all attempts), recent attempts, and real-only spend totals. `dashboard.py` keeps query semantics and turns those facts into display text, links, and chart geometry, and no longer reads storage. The direction `web → dashboard → analytics → storage` is enforced by tests, and the pages are byte-identical to before.

**Question:** Why does it matter strategically that analytics returns "natural values", when today only one HTML page consumes them?

## Answer

LLM Metrics is meant to feed more than a dashboard: a public JSON API, reports, a use-case recommendation layer, and later the Router and Exchange. All of them need the same facts (success rates, percentiles, costs, times) in machine form. If those facts only existed as HTML-ready strings like "75.0" or "unknown", every new consumer would either parse display text, which is fragile and lossy, or re-implement the statistics, which risks numbers that disagree between products.

Separating them now, while there is one consumer and the change is cheap, gives one source of truth for each number. The population rules that make the numbers trustworthy (failures count toward reliability but never as zero latency; simulated and real data never mix; unknown cost is never $0) live in one place that every product inherits.

The cost was one small, verified step: pages are byte-identical, and 242 tests pass.

## Critique

- **Good:** Cheap insurance for the multi-product plan, done before divergence could start. Credibility rules are centralized.
- **Weak:** It's a bet on future consumers. The API shape will only be validated when the first one exists. The sequence of four internal steps has delayed visible product progress.
- **Improve:** Make the next milestone consume `analytics` from a second surface, such as a small read-only JSON endpoint or a methodology report, so the investment pays off visibly. Then return to provider coverage.
