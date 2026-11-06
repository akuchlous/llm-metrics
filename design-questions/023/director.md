# Director — Step 023: bounded 15-minute collector

**Step context:** Step 023 added `llm_metrics.scheduled_collector`, a no-argument 15-minute OpenAI collector. A job-environment policy allows exactly 96 UTC quarter-hour slots (24 h). Each paid request is gated by a create-only GCS claim per slot, read back and checked against GCS server time, with a 7-minute late limit and expiry rechecked before the call. A slot is never retried. It also added `collector_audit` (claims vs records), structured log events with ERROR/missed-run alerts, a dedicated Cloud Run Job and service account holding the only key access, and an invoke-only scheduler identity. The pilot was activated for 2026-11-06T18:00Z–2026-11-07T18:00Z.

---

## Question

The project has now committed to unattended paid collection for a day. Was it right to go straight to 15-minute cadence instead of hourly, and what does this pilot need to prove before any public number is published?

## Answer

**Why 15 minutes straight away.** The risk that matters is unbounded or duplicated spend, and that is controlled by the slot gate and the 24-hour policy whatever the cadence. Going hourly would have collected 24 points instead of up to 96 for the same operational exposure.

The worst-case cost is tiny:

| Item | Cost per day |
|---|---|
| OpenAI, up to 96 × about $0.00033 | ≤ $0.032 |
| Cloud Run (worst case, outside the free tier) | ≤ about $0.13 |
| GCS | about $0.002 |
| **Total** | **≤ about $0.17**, against a $10/day guideline |

**What the pilot must prove before any publication:**
1. **Delivery:** at least 95% of the 96 slots recorded, with every gap explained by the audit (missed, refused or crash).
2. **No duplicates and no expiry violations:** at most one record per slot, none outside the window.
3. **Sound values:** stable data quality, meaning sane TTFT/latency distributions, no impossible values, and failures recorded as failures with nulls.
4. **Cost:** the billing export matches the estimate.

Even then, 96 samples from one model, one region and one day describe *that day*. Publishable claims need repeated windows, a methodology page (D069), and probably more than one region.

## Critique

**Good:**
- This converts infrastructure into data: the first real time series.
- It's bounded by design, and the cost is negligible next to its value.

**Weak / missing:**
- Single model, single region; a day of data invites over-interpretation.
- The post-window review depends on a human returning.

**Stronger:**
- Pre-register the acceptance criteria above.
- After review, schedule repeated bounded windows (not an indefinite schedule).
- Build historical aggregation and a static trends page only once at least one window meets the criteria.
