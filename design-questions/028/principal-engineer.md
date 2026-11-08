# Principal engineer — Step 028: production thresholds and metric snapshots

**Step context:** Step 028 (first part) added production publication thresholds (`static_site.production_gate`: complete 24-hour window, evidence for every slot, at least 50 successes, at most 5% unrecorded slots) and dated immutable metric snapshots (`/reports/YYYY-MM-DD/openai-ttft-measurements`, archived in the publication manifest under `metric_snapshots`). The complete OpenAI pilot (96 slots, 95 successes) passed and was published on llmxchange.com with its charts. The weekly cloud publisher and weekly cost editions are not built yet.

---

## Question

Where exactly is the production gate enforced, and can the old `--allow-preliminary` path still publish partial data publicly?

## Answer

- `static_site.build` applies `production_gate` to every real dataset outside staging. `publish_runner`'s metrics lane calls `build`, so `--allow-preliminary` can no longer push a partial window to production (tested: `ProductionGateTest`).
- Partial data can still be viewed only through the staging/preview `--provisional-metrics` path, which is `noindex, nofollow` and never archived.
- `plan_site` itself does not gate, so tests and previews can render fixtures; snapshots are created only for a dataset carrying the gate's label.

## Critique

Putting the gate in `build` rather than `plan_site` relies on all publication going through `build`; a future caller of `plan_site` + `freeze` would skip it. A follow-up could move the snapshot precondition into `freeze`.
