# Step 14c — Principal engineer

**Step context:** Step 014c split the dashboard's data interpretation from its presentation. New `llm_metrics/analytics.py` returns natural values (floats, ints, aware datetimes, None for unknown) for metric windows (successful observations with a nearest-rank summary, plus the success rate over all attempts), recent attempts, and real-only spend totals. `dashboard.py` keeps query semantics and turns those facts into display text, links, and chart geometry, and no longer reads storage. The direction `web → dashboard → analytics → storage` is enforced by tests, and the pages are byte-identical to before.

**Question:** Where did you draw the line between "analytics" and "presentation", and why did you choose dataclasses for some results but keep dictionaries for others?

## Answer

The line is whether a consumer other than this HTML dashboard would want the value as is.

- **Analytics:** the success rate as `0.75`, a percentile as `100.0`, a time as an aware `datetime`, unknown cost as `None`. A JSON API, report or recommendation engine all want these.
- **Presentation:** `"75.0"`, `"100.0 ms"`, `"2026-11-30 11:00 UTC"`, `"—"`, `"unknown"`, link targets, and SVG coordinates (which depend on this page's 800×300 canvas).

Population rules also belong to analytics: all attempts for the success rate, successful observations only for distributions, no mixing of environments, real-only spend with unknown cost as None. They are stated in the module and function contracts, so a new consumer gets them for free.

On representation: frozen dataclasses are used where field meaning is easy to confuse and costly to get wrong. `MetricWindow` carries two different populations side by side (`observations`: successful only; `reliability`: all attempts), and `SpendTotals.total_cost: float | None` encodes "unknown, not $0". The existing `outcomes.success_rate` dict and the storage row dicts stayed as they are: they're tested, their keys are already clear, and wrapping them would duplicate the schema without adding safety.

The rule is enforced, not just intended: `dashboard` may not import `storage`, `analytics` may not import `dashboard` or `web`, and `analytics` loads in a fresh process without any web package.

## Critique

- **Good:** One owner per concern, a rule simple enough to test, and an analytics API shaped for reuse without being built speculatively.
- **Weak:** There is only one consumer so far, so the API shape is unproven. The mix of dataclasses and dicts at the boundary is a judgment call that later contributors must understand.
- **Improve:** When the first JSON endpoint arrives, serialize `MetricWindow` and `Spend` directly and see whether the shapes hold. Promote attempt rows to a typed record if a second consumer needs them.
