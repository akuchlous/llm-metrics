# Step 018d — Director

**Step context:** Step 018d is a local integration-proof step: it found and fixed two correctness issues, ran 13 PostgreSQL tests, and explicitly produced no cloud resources or billable spend.

**Question:** What does the decision to require a local integration proof before any cloud provisioning reveal about the project's cost-risk model, and when does that model break down?

## Answer

The sequencing reflects a hierarchy of reversibility and cost. Local fixes are free and instant to retry; cloud provisioning incurs direct cost and takes time to tear down. By requiring that the storage layer work correctly against a real local PostgreSQL before provisioning Cloud SQL, the project ensures that the first cloud database connection succeeds, not discovers dialect bugs. The two bugs found in 018d (silent stamping and GROUP BY ordering) would have surfaced in Cloud SQL at provisioning time, requiring a code fix, a redeploy, and possibly a database rebuild — all at cloud cost and latency. The model breaks down when the local environment is not a close-enough proxy: if the Cloud SQL version, network latency, IAM authentication, or SSL requirements differ materially from localhost, the local integration proof is not transferable. For 018d, PostgreSQL 17 on localhost is close enough to Cloud SQL's standard PostgreSQL to trust the results. For the next step, the Cloud SQL connection method (Cloud SQL Auth Proxy, IP allowlist, or Unix socket) must also be tested, not assumed equivalent to localhost TCP.

## Critique

- **Good:** The cost-risk model is explicit and documented in DECISIONS.md; future contributors can read why the sequencing was chosen, not just what it was.
- **Weak:** "Local PostgreSQL = Cloud SQL" is an approximation. It misses Cloud SQL-specific authentication (IAM, proxy), TLS mode differences, and any Cloud SQL version-specific behaviour. A fully transferred proof would require a non-production Cloud SQL instance.
- **Improve:** Add a one-line caveat to the next step's prompt listing the Cloud SQL connection differences that must be re-verified even though Step 018d passed locally; this avoids treating the local proof as a cloud proof.
