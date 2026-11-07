# Senior manager — Step 027c: pilot charts and plan-only restart

**Step context:** Step 027c added per-request charts of the real OpenAI pilot to the metric page (TTFT, total response time and output tokens/s over UTC time, plus every slot outcome) from a new sanitized `llm-metrics.pilot-series.v1` file built by `llm_metrics.pilot_series` from the same validated mirror as the Step 024 summary, previewed with `./run.sh site-preview`, not deployed. It also added `./run.sh pilot-plan`, a plan-only command for a future bounded 24-hour run.

---

## Question

What do we need to decide tomorrow before another 24-hour run, and what will it cost?

## Answer

- First close the original pilot: approve and run `bash scripts/gcp/023_collector.sh stop`, run the post-window audit, and mark the run closed in `scripts/gcp/pilot_runs.json`. Until then `pilot-plan` refuses.
- Then pick a UTC start (a quarter hour, at least 30 minutes ahead) and run `./run.sh pilot-plan --start ... --analytics <reviewed summary>`. It prints the window, the 96 slots, what changes, and the stop/audit commands.
- Cost: at most 96 paid requests. From the pilot so far, about $0.03 expected (upper bound about $0.05) in estimated model API cost; GCP usage is expected within free tiers (not verified against billing).
- Launch needs a separate Approval C naming the run id, start and cost cap.

## Critique

The cost figures are estimates from token counts and list prices, not billed amounts. The registry update after each run is a manual step.
