# Lead engineer — Step 027b: real pilot metrics on staging

**Step context:** Step 027b put the first real OpenAI pilot measurements on the existing workers.dev staging site. A read-only private mirror of the pilot records and claims (86 of 96 slots due at 15:26Z on 2026-11-07) was summarized by the unchanged Step 024 `record_analytics`, then rendered through a new staging-only `--provisional-metrics` path: pilot gates, a "Partial pilot, as of 2026-11-07 15:30:00 UTC" label, an allowlisted public JSON, and a generated measured-evidence view at `/openai-ttft` because that answer is still a draft.

---

## Question

How does the code guarantee that a partial-window dataset can appear on staging but never on a production publication?

## Answer

- `_provisional_gate()` runs only when `provisional=True`, which the CLI accepts only as `--provisional-metrics` together with `--staging` (itself requiring `--preview-at`) and a `real` dataset; otherwise it raises.
- `publish_runner` (the production metrics lane) never passes `provisional`, and its existing gates still refuse partial days unless `--allow-preliminary` and refuse data that runs into the current UTC day.
- The gate requires collector slot evidence, at least `PROVISIONAL_MIN_SUCCESSES` (30) successes, and at most 5% of due slots without a record. It labels the window "Partial pilot" unless all 96 policy slots are due and recorded.
- Staging builds are `noindex, nofollow` with an empty sitemap and freeze nothing, so a provisional build cannot create a dated edition.
- `tests/test_site_provisional.py` covers each refusal, the label, the allowlisted JSON, the evidence page and the unchanged non-provisional path.

## Critique

The separation relies on two code paths staying separate; nothing stops a future change from passing `provisional` from the runner. A test that the runner module never references it would make that explicit.
