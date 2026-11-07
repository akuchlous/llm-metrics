# Principal engineer — Step 027c: pilot charts and plan-only restart

**Step context:** Step 027c added per-request charts of the real OpenAI pilot to the metric page (TTFT, total response time and output tokens/s over UTC time, plus every slot outcome) from a new sanitized `llm-metrics.pilot-series.v1` file built by `llm_metrics.pilot_series` from the same validated mirror as the Step 024 summary, previewed with `./run.sh site-preview`, not deployed. It also added `./run.sh pilot-plan`, a plan-only command for a future bounded 24-hour run.

---

## Question

How do we know the chart data is the same evidence as the analytics summary, and that it leaks nothing?

## Answer

- `pilot_series.build` reuses `record_analytics.load_records` and `slot_evidence` (the same validation and claim/record agreement), reads claims by their exact `claim_name`, and refuses if per-slot states disagree with the audit.
- It writes the same record manifest SHA-256 as the summary. `static_site.load_series` refuses the file unless the manifest hash, population and success/failure counts match the dataset, slots are in policy order, future slots match the cutoff, and every row has only allowlisted fields. The bytes must be canonical.
- The file holds slot times, states, failure categories and values rounded to 0.1 only: no attempt ids, object names, provider ids, prompts or responses (tested).

## Critique

Rounding to 0.1 ms is presentation; exact values stay in the private mirror. The series is staging/preview material; production publication still needs the Step 028 immutable metric snapshots.
