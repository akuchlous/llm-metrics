# Director — Step 027c: pilot charts and plan-only restart

**Step context:** Step 027c added per-request charts of the real OpenAI pilot to the metric page (TTFT, total response time and output tokens/s over UTC time, plus every slot outcome) from a new sanitized `llm-metrics.pilot-series.v1` file built by `llm_metrics.pilot_series` from the same validated mirror as the Step 024 summary, previewed with `./run.sh site-preview`, not deployed. It also added `./run.sh pilot-plan`, a plan-only command for a future bounded 24-hour run.

---

## Question

Is it worth running more 24-hour pilots of one model before adding anything else?

## Answer

- Repeat runs are cheap (cents) and turn one partial snapshot into evidence about stability across days; each run is a separate, comparable population by its policy window.
- The plan-only command keeps every run deliberate: bounded to 96 requests, no overlap, previous run closed, explicit approval.
- Charts of every request make the data's shape visible (a mostly steady TTFT with rare slow outliers), which is more honest than a single number.

## Critique

More runs of one model from one region still say nothing about other providers or locations. Scheduling runs one by one by hand does not scale; continuous collection would need a new, separately reviewed decision.
