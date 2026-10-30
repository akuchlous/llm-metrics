# Step 14c — Senior manager

**Step context:** Step 014c split the dashboard's data interpretation from its presentation. New `llm_metrics/analytics.py` returns natural values (floats, ints, aware datetimes, None for unknown) for metric windows (successful observations with a nearest-rank summary, plus the success rate over all attempts), recent attempts, and real-only spend totals. `dashboard.py` keeps query semantics and turns those facts into display text, links, and chart geometry, and no longer reads storage. The direction `web → dashboard → analytics → storage` is enforced by tests, and the pages are byte-identical to before.

**Question:** What does this refactor change for the people who will build the next features, and how do you keep them from blurring the boundary again?

## Answer

It gives every kind of change an obvious home:

- **A new statistic** (for example a p5 for throughput) goes in `analytics.py`, tested with plain numbers and no web stack.
- **A wording or format change** (decimals, "—", time format) goes in `dashboard.py`, tested by `ViewPreparationTest`.
- **A layout change** goes in a template.
- **A routing or header change** goes in `web.py`.

Reviewers can check placement quickly, and AI coding agents have a clear map from each module's docstring.

Keeping the boundary is mostly automatic:
- An AST test fails if `dashboard` imports `storage` or if `analytics` imports the dashboard or web layer.
- A fresh-process test fails if analytics starts pulling in Flask or Jinja.
- D059 in `DECISIONS.md` and each module's docstring describe the rule in plain words.

The rest is review discipline: a display string appearing in `analytics`, or a calculation appearing in a template, should be sent back.

## Critique

- **Good:** It lowers the cost and risk of the next features, and the guardrails are tests, not tribal knowledge.
- **Weak:** No user-visible change for the fourth step in a row, and the team may feel the refactor fatigue. Some rules (no display strings in analytics) can't be fully tested.
- **Improve:** Add a short "where does this change go?" table to `CODING_GUIDELINES.md`. Move to product work next and measure whether feature changes really touch only one layer.
