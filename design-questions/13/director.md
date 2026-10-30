# Step 13 — Director

**Step context:** Step 013 completed the Metrics v1 request data model. It added `output_tokens_per_s` (provider-reported output tokens over the first-to-last output chunk interval), a required `workload_id` naming the benchmark case, and `origin_cloud` / `origin_region` for where the runner executed (configured by environment variables, default `local` / `unknown`). Schema version 5 adds these as nullable request columns, NULL for historical rows.

**Question:** Why stop and finish the data model now, before adding providers, and why defer price discovery?

## Answer

Every attempt recorded without its workload or origin is permanently ambiguous: it can't later be placed in a coherent population. Adding these facts before more providers and before automation means the first comparable cross-provider data is born complete. That costs three columns and an env-var convention.

Tokens/s is the throughput users understand. Chunks/s depends on how each provider batches its stream, so it can't fairly compare providers. Tokens/s from provider-reported usage can, within the documented limits.

Price discovery is deferred deliberately. Verified prices in `pricing.py`, with the effective rates stored on every request, already make each cost explainable. Automated scraping or a price history adds operational surface whose value appears with Router and Exchange, not with Metrics v1.

## Critique

- **Good:** It front-loads the cheap, irreversible-if-missed decisions (identity of what was run and where) and defers the expensive, reversible ones. The scope stayed small: no registry, no dashboards, no new services.
- **Weak:** The product still has one real provider, one smoke workload and one successful real sample, so none of this is publishable yet. Tokens/s is still client-observed and needs careful wording in public.
- **Improve:** Make the next steps about coverage (a few providers on the same workload and origin) and a public methodology page that defines tokens/s, workload ids and origin before any comparison is published.
