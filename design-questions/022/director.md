# Director — Step 022: GCS-backed OpenAI pilot

**Step context:** Step 022 added an explicitly selected GCS results backend to `real_benchmark` (`LLM_METRICS_RESULTS_BACKEND=gcs`; gcp origin and OpenAI only). It checks configuration before the key, runs a real create/read/no-overwrite storage preflight before the paid request, fixes the attempt id before the request and exits 3 if the record is not confirmed durable. It added a storage-only `gcs_smoke` command. In the cloud, the job service account proved storage with no provider key (Phase A), then one paid `gpt-6-luna` attempt was stored as an immutable `prod` object and independently verified (Phase B). The key was detached afterwards.

---

## Question

The project can now store a real measurement without any database. Is the pipeline ready to start producing the dataset the product needs, and what should the next investment buy?

## Answer

**What changed economically:**

| Approach | Model cost | Other cost | Manual effort |
|---|---|---|---|
| Step 020 (per-run Cloud SQL) | about $0.0003 | about $0.004 of infrastructure | about 25 minutes of provisioning |
| Step 022 (GCS) | about $0.0003 | under $0.003 of job time; storage effectively free | none per run |

The standing cost is about $0/month. At 96 runs/day, rough monthly costs:
- OpenAI: about $0.95
- GCS: about $0.02–0.05
- Cloud Run job time: about $0–5

That is well under $10/day.

**Readiness:** the mechanism is ready; the operations are not. A single run doesn't show:
- behaviour across GCS or OpenAI incidents
- missed-run accounting
- alerting
- the unclosed crash window

Scheduling should start cautiously (hourly, OpenAI-only, budget-capped, alerting on exit 3 and missed runs) and earn its way to 15-minute cadence.

**Credibility:** every number published later will trace to an immutable object with a SHA-256, a fixed schema, a stored price basis and explicit nulls. That auditability is a differentiator for a metrics product.

## Critique

**Good:**
- This removes the last manual, standing-cost component.
- The spend was trivial, and the path is reproducible from committed scripts.

**Weak / missing:** after many steps there are still only three real data points. Without a dated data target, the project risks perfecting infrastructure instead of collecting data.

**Stronger:** approve Step 023 against a concrete outcome. For example: "≥ 95% of hourly slots produce a record over 14 days, under $1/day, no lost billed attempts", followed by the first static snapshot (D069).
