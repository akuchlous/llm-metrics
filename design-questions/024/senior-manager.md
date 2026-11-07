# Senior manager — Step 024: offline analytics from immutable records

**Step context:** Step 024 added `llm_metrics.record_analytics`, an offline, read-only command that reads a local mirror of the immutable `llm-metrics.attempt.v1` GCS records (prod only), selects one exactly filtered population (provider, model, profile, workload, origin, UTC `[start, end)`), validates every candidate file with `object_results.decode_record`, and writes a canonical, create-only `llm-metrics.analytics.v1` summary. Slot completeness is reported only from collector claims via `collector_audit.audit`. It was tested on committed synthetic fixtures; no cloud or provider access was used.

---

## Question

When the 24-hour pilot ends, you'll want to tell stakeholders "OpenAI gpt-6-luna TTFT p95 is X ms with Y% success". What can this summary support honestly today, and what must not be said yet?

## Answer

**It can support**, for one exact population (`openai.gpt-6-luna.v1`, `interactive-chat-v1`, `gcp/us-central1`, a stated UTC window):
- observed success rate over the recorded attempts, with failures by category;
- p50/p95/min/max/latest TTFT and total latency over successes only, plus tokens/s;
- known model spend, with failed attempts counted as cost-unknown;
- if claims are supplied, how many scheduled slots ran, failed, or produced nothing;
- a hash list of every record used, so anyone with the mirror can reproduce the file byte for byte.

**It must not be stated as:**
- Provider uptime. The `observed_success_rate` caveat says this is one runner, one origin, one workload.
- A precise p95. About 95 successes give a usable but noisy p95. Below 20 successes, nearest-rank p95 is simply the maximum (`p95_is_sample_max`). Below 100 successes, the `small_sample` caveat is set.
- A ranking or comparison. There is one provider, one model, one day.
- "Every slot succeeded", unless slot evidence was supplied and shows it.

The caveats are machine-readable codes in the file itself, so a future page cannot drop them without dropping data.

## Critique

**Good:** the honest-claims boundary is encoded in the artifact rather than left to whoever writes the update. Spend is reported as known plus unknown, never as a falsely complete total.

**Weak / missing:**
- There are no confidence intervals. "p95 of 95 samples" still reads more precise than it is.
- One day can't separate time-of-day effects from noise.
- The real Step 023 mirror has not been run through it yet, because the pilot is still active.

**Stronger:** add a bootstrap or order-statistic interval for p95 in a later schema version, and wait for more than one full day before any external number.
