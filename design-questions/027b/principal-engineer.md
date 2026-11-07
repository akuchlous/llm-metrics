# Principal engineer — Step 027b: real pilot metrics on staging

**Step context:** Step 027b put the first real OpenAI pilot measurements on the existing workers.dev staging site. A read-only private mirror of the pilot records and claims (86 of 96 slots due at 15:26Z on 2026-11-07) was summarized by the unchanged Step 024 `record_analytics`, then rendered through a new staging-only `--provisional-metrics` path: pilot gates, a "Partial pilot, as of 2026-11-07 15:30:00 UTC" label, an allowlisted public JSON, and a generated measured-evidence view at `/openai-ttft` because that answer is still a draft.

---

## Question

The published dataset JSON used to be the exact validated summary, identified by its SHA-256. What changed, and does the public file still prove what was validated?

## Answer

- In a provisional preview the public file is an allowlisted projection: `evidence.records` (object names and attempt ids), `slot_completeness.problems` (attempt ids) and `metrics.*.latest` (attempt ids) are removed. A `public_projection` block names the removed fields and `of_dataset_sha256`, the hash of the private validated summary (763fd4b0…).
- The page shows both hashes: the dataset SHA-256 (private, validated) and the published summary SHA-256 (42d8217b…). The record manifest hash (48c45316…) still commits to the exact record set.
- Production builds are unchanged: without `provisional` the exact summary is published as before (D082).

## Critique

A reader cannot recompute the private hash from the public file; they must trust the projection rule. Applying the same allowlist to production publications is a decision for Step 028.
