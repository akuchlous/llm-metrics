# Step 018h — Senior manager

**Step context:** Step 018h adds a fail-closed guard in `real_benchmark.run()` that
rejects non-local-origin paid benchmark calls unless `LLM_METRICS_DATABASE_URL` is
explicitly set to a PostgreSQL URL, preventing silent data loss to ephemeral
container storage.

**Question:** Step 018h ships a code change that protects the local codebase but
explicitly notes that the deployed Cloud Run Job still runs the old image and
remains vulnerable. How do you decide whether this is an acceptable state, and what
does the next step need to include to close it?

## Answer

This state is acceptable for two reasons specific to this project's context:

First, the Cloud Run Job is not on a schedule; it runs only on explicit manual
invocation (`gcloud run jobs execute`). The residual risk is bounded: a manually
triggered mistake costs one request (~$0.0003) and loses that one result. That risk
was already present before 018h; nothing made it worse. The step's documentation
creates explicit awareness of it.

Second, closing the residual risk requires provisioning a new PostgreSQL database
first — which is a separately approved step (018i). Without a DB URL to inject into
the job, rebuilding and redeploying the image would not fix the root issue anyway;
the job would just run the new guard and refuse immediately.

The acceptable decision: land the code change now so the guard is present in the
source branch, document the gap clearly, and close it in 018i when the full
deploy-with-database sequence is authorized.

For 018i to close the gap it must:
1. Provision a Cloud SQL instance (separately approved).
2. Create a secret for `LLM_METRICS_DATABASE_URL`.
3. Rebuild the image (`gcloud builds submit`).
4. Update the job to reference the new image, the new secret, and Cloud SQL.
5. Verify: run the job with no DATABASE_URL set → guard should reject → confirms
   the guard is live.
6. Run one real measurement with the full configuration.

Until 018i completes, the deployment documentation should note that the existing job
must not be executed manually.

## Critique

- **Good:** The step is narrowly scoped (code only, no cloud changes), making it
  safe to land quickly without an approval gate. Explicit documentation of the
  residual risk and "do not execute the job" guidance prevents accidental spend.
- **Weak:** The step does not include an automated enforcement mechanism — for
  example, a Cloud Run Job condition that would cause job execution to fail if
  DATABASE_URL is absent. The guard only protects code that has been deployed.
- **Improve:** When 018i deploys the new image, add an explicit verification step
  (attempt a dry-run job execution with DATABASE_URL unset, confirm exit code 2,
  then proceed with the full configuration). This creates a reproducible deployment
  smoke test that closes the verification loop.
