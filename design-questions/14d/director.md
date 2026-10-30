# Step 14d — Director

**Step context:** Step 014d added one versioned, read-only JSON endpoint, `GET /api/v1/metrics?metric=&window=`, that returns the aggregate page's data as facts: JSON numbers, `null` for unknown, ISO 8601 UTC times. It names its population (simulated dummy provider), metric and unit, and window; `samples` summarizes successful observations only and `reliability` counts every attempt. Shared query definitions moved from `dashboard.py` to a small `query.py`; a Flask-free `api.py` serializes analytics results; `web.py` encodes JSON and sets statuses. HTML pages are byte-identical to 014c.

**Question:** What does a versioned JSON API change about what LLM Metrics is, and what risks does it create?

## Answer

It turns LLM Metrics from a website into a data source. A Router, a report, or another team's dashboard can now read the same measurements as the page, with population, units and sample sizes attached, instead of scraping HTML. That is the path to the product's purpose: decisions made from measured provider behavior.

Risks:
- **Compatibility becomes a commitment.** Once someone depends on v1, changing a field's meaning is a breaking change. Mitigation: the contract is documented, additive-only, and v2 is the escape hatch.
- **Misreading simulated data.** Mitigation: every response names its population; nothing implies real performance.
- **Overclaiming.** The API returns observed counts, rates and percentiles only: no rankings, recommendations, uptime or SLA claims.
- **Exposure.** It is local-only today. Public hosting will need authentication, rate limits and abuse controls before the API leaves 127.0.0.1.

## Critique

- **Good:** A narrow, factual interface that is easy to keep stable, built on the analytics layer instead of beside it.
- **Weak:** Its value depends on real-provider data, scheduling and more models, none of which exist yet.
- **Improve:** Tie the next API change to a real consumer's need (for example the Router's first question) rather than adding endpoints speculatively.
