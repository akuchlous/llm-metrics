# Senior manager — Step 027b: real pilot metrics on staging

**Step context:** Step 027b put the first real OpenAI pilot measurements on the existing workers.dev staging site. A read-only private mirror of the pilot records and claims (86 of 96 slots due at 15:26Z on 2026-11-07) was summarized by the unchanged Step 024 `record_analytics`, then rendered through a new staging-only `--provisional-metrics` path: pilot gates, a "Partial pilot, as of 2026-11-07 15:30:00 UTC" label, an allowlisted public JSON, and a generated measured-evidence view at `/openai-ttft` because that answer is still a draft.

---

## Question

What exactly can someone see on staging now, and what must not be said about it?

## Answer

- `/openai-ttft` and `/metrics/openai/ttft` show real measurements from 86 due slots (85 successes, 1 provider error, 0 missing) between 2026-11-06 18:00 and 2026-11-07 15:30 UTC: TTFT median 1,637 ms and p95 2,551 ms, total response time median 4,279 ms, output speed median 116.7 tokens/s, observed success rate 98.8%.
- Every value carries "Partial pilot, as of 2026-11-07 15:30:00 UTC; not a 24-hour result or provider-wide benchmark" and a small-sample caution. The estimated model cost is labelled as estimated from tokens and list prices, not as billed cost.
- Not to be said: that this is OpenAI's TTFT in general, a 24-hour result, a ranking, or published production data.

## Critique

Staging is public (only unindexed); anyone with the URL sees provisional numbers. The value of the pilot depends on the final audit after 18:00Z.
