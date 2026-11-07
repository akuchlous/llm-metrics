# Lead engineer — Step 027c: pilot charts and plan-only restart

**Step context:** Step 027c added per-request charts of the real OpenAI pilot to the metric page (TTFT, total response time and output tokens/s over UTC time, plus every slot outcome) from a new sanitized `llm-metrics.pilot-series.v1` file built by `llm_metrics.pilot_series` from the same validated mirror as the Step 024 summary, previewed with `./run.sh site-preview`, not deployed. It also added `./run.sh pilot-plan`, a plan-only command for a future bounded 24-hour run.

---

## Question

How do the charts avoid misleading a reader about gaps, outliers and what a point means?

## Answer

- One row per policy slot (always 96). Each dot is one request; the page says so, and nothing is called an average or a trend.
- Lines join only consecutive successful slots. A failure, a missing slot or a claim without a record breaks the line and gets an ✕ on the time axis; future slots sit in a shaded "not yet due" band. A success without a reported throughput is a gap, counted in the caption.
- If the largest value is more than twice the p95, the axis stops at a round number above 2 x p95 and the slower requests are drawn as ▲ at the top edge with their actual value written beside them. The caption says so. For the pilot, one slow request (12,343 ms TTFT, 15,236 ms total) is shown this way.
- The median is a dashed line labelled nearest-rank with n. Every chart has a title, description and caption, and a 96-row table sits in a `<details>` fallback.
- Tests: segment breaks at failure/missing/claim-without-record, future band, throughput n, the clipping rule, axis rounding, accessible markup, no inline styles or scripts.

## Critique

A capped axis is a judgment call; some readers will want a log scale. The charts were checked through HTML and tests only, because no browser was available in this session, so the visual review in `site-preview` is still needed.
