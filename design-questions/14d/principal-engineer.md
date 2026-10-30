# Step 14d — Principal engineer

**Step context:** Step 014d added one versioned, read-only JSON endpoint, `GET /api/v1/metrics?metric=&window=`, that returns the aggregate page's data as facts: JSON numbers, `null` for unknown, ISO 8601 UTC times. It names its population (simulated dummy provider), metric and unit, and window; `samples` summarizes successful observations only and `reliability` counts every attempt. Shared query definitions moved from `dashboard.py` to a small `query.py`; a Flask-free `api.py` serializes analytics results; `web.py` encodes JSON and sets statuses. HTML pages are byte-identical to 014c.

**Question:** Walk through the v1 response contract. Which decisions will be hardest to change later, and why did you make them this way?

## Answer

Hardest to change, because callers will depend on them:

1. **`samples` and `reliability` are separate objects.** They are different populations: successful observations versus every attempt. Putting `count` next to `success_rate` in one flat object would invite callers to treat them as the same denominator. Seeded history even makes `samples.count` larger than `reliability.attempts`, which is documented rather than hidden.
2. **`null` versus 0.** Counts are always integers (0 attempts is a true count), but rates, percentiles, and the latest value are `null` when there is nothing to describe. Changing that later would break callers who rely on it.
3. **Time format.** One format everywhere: ISO 8601 UTC with microseconds and `Z`, the same as stored `recorded_at`. Fixed width makes it sortable as text.
4. **Percentile keys `p50`/`p95`/`p99`.** Strings, because JSON object keys are strings anyway; the `p` prefix avoids `"50"` being read as a value.
5. **`population.data: "simulated"`.** Uses the product word the dashboard already uses (`/requests?data=simulated`), not the storage word `test`, so internal naming can change without breaking the API.

Easy to change: adding fields such as a `real` population or a provider selector, which is additive.

Deliberately left out: a metric label ("TTFT" is presentation), formatted values, and generated-at time (`window.end` is the request time).

## Critique

- **Good:** The response explains itself: population, unit, window and the two populations are explicit, so a Router team does not need to read our code.
- **Weak:** `population` has a single possible value today; when real-provider selection arrives, the meaning of "aggregate" (one model? a provider?) must be designed, and the shape may need a list. Full-precision floats expose noise digits.
- **Improve:** Publish a small JSON example per field in tests (golden body) so any contract change shows up as a diff in review.
