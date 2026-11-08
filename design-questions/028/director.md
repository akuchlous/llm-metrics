# Director — Step 028: production thresholds and metric snapshots

**Step context:** Step 028 (first part) added production publication thresholds (`static_site.production_gate`: complete 24-hour window, evidence for every slot, at least 50 successes, at most 5% unrecorded slots) and dated immutable metric snapshots (`/reports/YYYY-MM-DD/openai-ttft-measurements`, archived in the publication manifest under `metric_snapshots`). The complete OpenAI pilot (96 slots, 95 successes) passed and was published on llmxchange.com with its charts. The weekly cloud publisher and weekly cost editions are not built yet.

---

## Question

Is one complete 24-hour pilot enough to publish numbers publicly?

## Answer

- Yes, as a dated, scoped observation: the thresholds require a complete window with evidence for every slot and enough successes, and the page says what it is and is not. The snapshot freezes the numbers so later runs never rewrite them.
- It is not enough for comparisons or general claims about OpenAI; those need repeated runs, more regions and providers.

## Critique

The thresholds (50 successes, 5% unrecorded) are judgment calls set for this pilot; they should be revisited before multi-provider publication.

---

## Question (part 2: weekly publisher)

What is still needed before the site updates itself every week in production?

## Answer

- Phase 0 is done offline and tested. Approval A: create the least-privilege publisher SA, a scoped Cloudflare token and a paused job, and prove it on staging. Approval B: point it at production and resume the schedule.
- Until then, publishing stays a manual, owner-requested action.

## Critique

New metrics still require someone to run analytics and upload reviewed inputs; the weekly job automates publication, not measurement.
