# Principal engineer — Step 022: GCS-backed OpenAI pilot

**Step context:** Step 022 added an explicitly selected GCS results backend to `real_benchmark` (`LLM_METRICS_RESULTS_BACKEND=gcs`; gcp origin and OpenAI only). It checks configuration before the key, runs a real create/read/no-overwrite storage preflight before the paid request, fixes the attempt id before the request and exits 3 if the record is not confirmed durable. It added a storage-only `gcs_smoke` command. In the cloud, the job service account proved storage with no provider key (Phase A), then one paid `gpt-6-luna` attempt was stored as an immutable `prod` object and independently verified (Phase B). The key was detached afterwards.

---

## Question

The first GCS-backed measurement succeeded end to end. What still stands between this path and an *unattended* collector whose dataset you would defend scientifically, and which gaps are architectural rather than operational?

## Answer

**What is now proven:**
- With a real bucket and the real job identity, a paid attempt becomes exactly one immutable canonical object whose bytes match the job log's SHA-256.
- Its facts match the SQL schema, including cached tokens, the price basis and the null rules.
- There is no standing database. SQL mode and the 018h guard are untouched, so the two backends can't silently mix: GCS needs `LLM_METRICS_RESULTS_BACKEND=gcs`, and the GCS target variables alone don't select it.

**Architectural gaps:**
1. **The crash window.** Response → write is not atomic. Exit 3 handles a surviving process, but a killed container loses a billed attempt, identifiable only by the attempt id printed before the request. A real fix needs a durable intent written *before* the request (for example a `pending/<attempt_id>` object) that is reconciled afterwards, with the population rules updated so a missing outcome is counted rather than silently dropped.
2. **Missed-run accounting.** With scheduling, "no object" could mean a missed trigger, a pre-request refusal or a crash. Availability metrics need an expected-run ledger independent of the result objects.
3. **No reconciliation against provider usage.** Cost is derived from provider-reported tokens and stored rates; it isn't checked against billing.
4. **Synthetic and real records share a bucket.** They're separated by the `env` path segment, which readers must respect.

**Operational gaps:** a probe lifecycle rule, alerting on exit 3 and on missed runs, and a budget alarm per day.

## Critique

**Good:**
- Each new piece of risk (storage, then money) was isolated and proven before the next.
- The record's identity and integrity hold end to end (announced id = record id = object name; SHA-256 matches).

**Weak / missing:** the crash window is documented rather than reduced, and n = 1 GCS record says nothing about the behaviour under load or during GCS incidents.

**Stronger:** before scheduling at 15-minute cadence, add the pending-intent object and an expected-run ledger, so every scheduled slot ends in exactly one of {record, refused-before-request, lost-after-request}.
