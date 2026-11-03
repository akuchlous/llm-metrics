# Step 018c — Director

**Step context:** Step 018c is a deliberate pre-deployment micro-step: prove the storage boundary is PostgreSQL-capable before spending on cloud infrastructure, keeping the increment reviewable and reversible.

**Question:** Why was PostgreSQL readiness separated into its own step rather than combined with cloud provisioning, and what does that sequencing decision reveal about the project's review discipline?

## Answer

The sequencing reflects a principle of separating verifiable software changes from infrastructure spend. Combining dialect correctness with Cloud SQL provisioning would mean that a storage bug discovered during cloud setup requires either a re-deploy or a rollback of infrastructure that costs money while idle. By proving dialect correctness offline first — with compile-level SQL tests, an updated driver dependency, and an explicit "not yet verified" label in the output — the project can get a meaningful review of the storage boundary before any resource is created. The review boundary is also smaller: the 018c diff is storage code and tests; the 018d diff will be infrastructure configuration and a smoke test. Each can be reviewed independently, and a problem in either does not contaminate the other.

## Critique

- **Good:** Makes the cost and reversibility asymmetry explicit: a rejected 018c diff costs nothing; a rejected 018d diff with provisioned infrastructure costs money and requires teardown.
- **Weak:** The overhead of extra micro-steps adds latency to the overall deployment timeline; a team under schedule pressure might resist this discipline.
- **Improve:** Capture the sequencing rationale in a DECISIONS.md entry (D066 covers the dialect details but not the why-now sequencing argument) so future contributors understand this is an explicit policy, not an accident of context.
