# Director — Step 024: offline analytics from immutable records

**Step context:** Step 024 added `llm_metrics.record_analytics`, an offline, read-only command that reads a local mirror of the immutable `llm-metrics.attempt.v1` GCS records (prod only), selects one exactly filtered population (provider, model, profile, workload, origin, UTC `[start, end)`), validates every candidate file with `object_results.decode_record`, and writes a canonical, create-only `llm-metrics.analytics.v1` summary. Slot completeness is reported only from collector claims via `collector_audit.audit`. It was tested on committed synthetic fixtures; no cloud or provider access was used.

---

## Question

The project now has two analytics paths: the SQL-backed Flask dashboard and this file-based summary over GCS records. Is building a hand-rolled offline summary file the right investment, compared with loading records into a managed analytics service (for example BigQuery) or reusing the SQL path?

## Answer

**For the current stage, yes:**
- **Cost and risk.** It runs locally, uses no paid resource, and needs no new service account or dataset. The project target is ≤ $10/day, and Step 023 spends about $0.03/day on the model. A managed warehouse adds IAM, a load path and a billing surface for under 100 rows a day.
- **Trust.** The summary is computed only from the immutable, create-only records, validated by the same code that wrote them, with per-record SHA-256s. That is a stronger provenance story than a mutable SQL table for a project whose product is credibility.
- **Product fit.** D069 already chose static HTML plus versioned JSON snapshots, with no always-on public service. `llm-metrics.analytics.v1` is that snapshot contract. A future page reads only this file, never provider APIs or the bucket.
- **Reuse, not reinvention.** Validation, percentiles, outcome rates and slot states are imported from existing modules. The new code is filtering, aggregation and an atomic writer, all standard library.

**When to revisit:** multiple providers, regions and workloads at 15-minute cadence over months (tens of thousands of records), ad-hoc slicing needs, or a public API. At that point a columnar export (Parquet in GCS) or BigQuery external tables over the same immutable objects would scale without giving up the evidence model.

## Critique

**Good:** it keeps the product's integrity story intact, and keeps scope small and cheap. It also fits the already-decided static-publishing direction.

**Weak / missing:**
- The SQL dashboard and this summary can now disagree, and nothing reconciles them. The old path should be retired or explicitly labelled legacy.
- Getting the mirror is a manual `gcloud storage cp`, an operator step with no automation or audit trail yet.

**Stronger:** decide (in a DECISIONS entry) that the GCS records plus this summary are the source of truth for published numbers. Plan a bounded, approved step that produces the mirror reproducibly, for example a read-only service account with a checksum-verified copy.
