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

---

## Question (part 2: weekly publisher)

Why can new numbers never silently contradict an approved answer?

## Answer

- Methodology answers are refused if their prose states measured values (`_EMPIRICAL_RE`); numbers appear only in generated sections.
- Dataset-based answers are still refused at build time; the weekly report marks any such answer reviewed against another dataset `review_needed`, and that holds the metrics update for the whole site.
- The job never approves or edits prose; a revised answer is a new edition approved by a person.

## Critique

Holding all metrics for one stale answer is coarse; per-page holds would be better once dataset-based answers exist.
