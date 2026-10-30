# Step 13 — Senior manager

**Step context:** Step 013 completed the Metrics v1 request data model. It added `output_tokens_per_s` (provider-reported output tokens over the first-to-last output chunk interval), a required `workload_id` naming the benchmark case, and `origin_cloud` / `origin_region` for where the runner executed (configured by environment variables, default `local` / `unknown`). Schema version 5 adds these as nullable request columns, NULL for historical rows.

**Question:** How should a team running this across several clouds configure origin, and what operational risks does the design leave?

## Answer

Each runner deployment sets two environment variables, for example `LLM_METRICS_ORIGIN_CLOUD=aws` and `LLM_METRICS_ORIGIN_REGION=us-east-1`. Nothing is inferred from IP addresses, geolocation or cloud metadata services, so a result's origin is exactly what the deployment declared.

Unset means `local` / `unknown`, so a developer laptop never pretends to be a cloud region.

Values are checked conservatively: lowercase letters, digits and hyphens, at most 63 characters. A typo like `US-East-1` stops the run with exit code 2 before any paid request, instead of quietly creating a new "region" in the data. The error doesn't echo the value.

The same discipline applies to workloads: the id is a constant in code (`simulated.default.v1`, `smoke.short_text.v1`), not a free-form runtime input.

## Critique

- **Good:** It's explicit, deterministic and auditable, and it fails closed before spend. There are no new dependencies or metadata calls that could hang or leak credentials.
- **Weak:** A misconfigured but well-formed value (`us-east-2` on a `us-east-1` host) is accepted silently. There's no list of expected origins, and no view yet to spot an unexpected one.
- **Improve:** Make origin variables part of the deployment template with a reviewed value per environment. When deployment starts, alert on an origin not in the deployment inventory, and show the distinct origins per day on the requests page.
