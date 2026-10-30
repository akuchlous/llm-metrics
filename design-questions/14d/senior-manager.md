# Step 14d — Senior manager

**Step context:** Step 014d added one versioned, read-only JSON endpoint, `GET /api/v1/metrics?metric=&window=`, that returns the aggregate page's data as facts: JSON numbers, `null` for unknown, ISO 8601 UTC times. It names its population (simulated dummy provider), metric and unit, and window; `samples` summarizes successful observations only and `reliability` counts every attempt. Shared query definitions moved from `dashboard.py` to a small `query.py`; a Flask-free `api.py` serializes analytics results; `web.py` encodes JSON and sets statuses. HTML pages are byte-identical to 014c.

**Question:** Why ship an API with one endpoint and one simulated population, and what would you tell a team that wants to start building on it tomorrow?

## Answer

The goal was to prove the 014c boundary with a second real consumer, not to launch a product API. One endpoint was enough to show that:

- analytics results can be reused without parsing display strings;
- the HTML and JSON outputs cannot drift (shared parser and loader);
- errors, privacy and security behave predictably for programs, not only for browsers.

What I would tell a consuming team:

- **Safe to rely on:** the field names, types, units and `null` semantics in the README table; `/api/v1/` will only gain fields.
- **Not yet meaningful:** the data. `population.data` is `"simulated"`; the numbers are not real LLM performance.
- **Not provided:** authentication, CORS, rate limits, other endpoints, or provider/model selection. It is served on 127.0.0.1 only.
- **Ignore unknown fields**, so additive changes never break you.

Cost of the step: three small modules touched (`query`, `api`, `web`), 20 new API tests, and no change to any page.

## Critique

- **Good:** Small scope, explicit contract, and honest labelling of the data.
- **Weak:** A contract with no real data invites premature dependence; teams may build against simulated numbers and be surprised by real variance and failures.
- **Improve:** Before announcing it, add the real-provider population and agree on who owns API compatibility decisions.
