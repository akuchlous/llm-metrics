# Director — Step 027b: real pilot metrics on staging

**Step context:** Step 027b put the first real OpenAI pilot measurements on the existing workers.dev staging site. A read-only private mirror of the pilot records and claims (86 of 96 slots due at 15:26Z on 2026-11-07) was summarized by the unchanged Step 024 `record_analytics`, then rendered through a new staging-only `--provisional-metrics` path: pilot gates, a "Partial pilot, as of 2026-11-07 15:30:00 UTC" label, an allowlisted public JSON, and a generated measured-evidence view at `/openai-ttft` because that answer is still a draft.

---

## Question

Was it right to show real but partial numbers now, rather than waiting for the complete 24-hour pilot?

## Answer

- Yes, for staging only: it validates the whole path (immutable records, deterministic analytics, gates, static rendering, Cloudflare) on real data, with conspicuous provisional labelling and no indexing.
- It did not lower any production gate: production publication still needs the complete window, the Step 028 immutable metric snapshots and Approval B.
- The draft metric answer was not approved just because data exists; a generated evidence view shows only numbers.

## Critique

Showing early numbers creates pressure to treat them as results. The provisional figures will be superseded after the window closes, and the scheduler and key remain attached until the separately approved `stop`.
