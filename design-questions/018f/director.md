# Step 018f — Director

**Step context:** Step 018f is the first controlled OpenAI measurement on Google Cloud. The step also records a strategic architecture decision: public LLM Metrics will publish via static HTML and versioned JSON snapshots behind a CDN, not a continuously running public Flask/Cloud Run service.

**Question:** The team chose static HTML + versioned JSON snapshots over a continuously running public Flask service. What does this decision cost and what does it buy, strategically?

## Answer

A continuously running public web service on Cloud Run would have the simplest developer experience (one `gcloud run deploy`) and the most flexible UI (live queries, filters, date ranges). But its always-on cost (~$8–11/month for Cloud SQL alone, plus service CPU and egress) would be incurred even before the first publishable benchmark result. More importantly, it creates a security perimeter that must be maintained indefinitely: a public Flask endpoint with no authentication would need a WAF, rate limiting, and ongoing CVE patching — work that generates no measurement value.

Static HTML + versioned JSON snapshots change the cost structure: the database runs privately (or not at all between job runs), snapshots are generated once per benchmark run and pushed to object storage or a CDN, and there is no always-on attack surface. Future Router/Xchange consumers can read cached snapshots without a live database query. The public site costs roughly the CDN egress of a few hundred kilobytes per visitor — essentially zero at this scale.

The tradeoff is real-time flexibility: live filters, date-range queries, and per-provider comparisons require either pre-generating many snapshot variants or a dynamic query layer. The team accepts this constraint explicitly, treating the static site as the first publication format and deferring a dynamic query API to when it is justified by demand.

## Critique

- **Good:** The decision eliminates the largest recurring cost and attack surface before the first result is published. It aligns cost with actual value delivered (a snapshot is generated when there is something to show).
- **Weak:** "Static HTML + versioned JSON" defers the question of *how* the snapshot is generated and published. Without a defined snapshot generation pipeline and CDN configuration, this is a direction, not a plan. The first version of the static publisher must be scoped and staffed before 018f Stage B.
- **Improve:** Define the snapshot contract now — what JSON fields does each versioned snapshot contain, what is the URL pattern (`/snapshots/v1/YYYYMMDD.json`), and what triggers a publish (each Cloud Run Job completion, or a separate scheduled publisher)? Locking the schema before the first real measurement avoids a schema migration when the first consumer (Router/Xchange) onboards.
