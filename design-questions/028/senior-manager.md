# Senior manager — Step 028: production thresholds and metric snapshots

**Step context:** Step 028 (first part) added production publication thresholds (`static_site.production_gate`: complete 24-hour window, evidence for every slot, at least 50 successes, at most 5% unrecorded slots) and dated immutable metric snapshots (`/reports/YYYY-MM-DD/openai-ttft-measurements`, archived in the publication manifest under `metric_snapshots`). The complete OpenAI pilot (96 slots, 95 successes) passed and was published on llmxchange.com with its charts. The weekly cloud publisher and weekly cost editions are not built yet.

---

## Question

What is public now, and what remains of Step 028?

## Answer

- Public on llmxchange.com: the metric page with the complete pilot (TTFT median 1,631 ms, p95 2,594 ms; total 4,241 ms; 117.8 tokens/s; 95 of 96 succeeded), the four charts, and a frozen 2026-11-08 snapshot. The page states scope: one model, one workload, one region, not a ranking.
- Remaining: the weekly cloud trigger (Cloud Scheduler plus a Cloud Run job; needs Approval A for staging and B for production), weekly dated cost editions, an "answer review needed" report, and billing exports. None of these were started.

## Critique

Publishing before the weekly workflow exists means updates are manual for now. The p95 comes from 95 successes and is labelled a small sample.

---

## Question (part 2: weekly publisher)

What does the weekly job cost, and how is that shown without inventing a figure?

## Answer

- Expected USD 0 (free tiers: one scheduler job, a few minutes of Cloud Run per month, KB of storage); under USD 0.10/month even without free tiers.
- /costs lists it under "Weekly publishing operations" as "pending reconciliation" until a billing statement shows the real charge; estimates are never added to totals.

## Critique

Free-tier assumptions are per billing account and can change; the first monthly statement after Approval A must be checked.
