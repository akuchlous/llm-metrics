# Step 018h — Principal engineer

**Step context:** Step 018h adds a fail-closed guard in `real_benchmark.run()` that
rejects non-local-origin paid benchmark calls unless `LLM_METRICS_DATABASE_URL` is
explicitly set to a PostgreSQL URL, preventing silent data loss to ephemeral
container storage.

**Question:** The guard relies on `LLM_METRICS_ORIGIN_CLOUD` being operator-declared;
it cannot cryptographically verify that the process is actually running in a cloud
container. What failure modes does this leave open, and what would a stronger design
look like?

## Answer

The guard is a configuration safety net, not a security boundary. Its failure modes:

1. **Local override escapes the guard.** If `LLM_METRICS_ORIGIN_CLOUD` is unset or
   set to `local` (the default) in a cloud container — for example by a misconfigured
   job update — the guard skips and falls back to SQLite. The job succeeds, spends
   ~$0.0003, and silently discards the result.

2. **Operator error on the other side.** If a local developer sets
   `LLM_METRICS_ORIGIN_CLOUD=gcp` and also sets a PostgreSQL URL to point at a
   shared database, the guard passes. No code prevents a local run from writing to a
   production database; the distinction is in the declared environment, not in
   enforcement.

3. **The guard passes; the DB fails mid-run.** The existing `storage.connect()`
   preflight fires before the paid call, so a completely unreachable DB is caught.
   But a DB that is reachable at preflight but unavailable during the write (e.g.
   Cloud SQL connection limit exceeded after the request returns) would leave a
   billed but unrecorded attempt.

A stronger design could:
- Read the cloud metadata endpoint (`http://metadata.google.internal/...`) to detect
  GCP, rather than relying on an env var. This survives operator forgetfulness but
  adds a network call and fails offline.
- Require the PostgreSQL URL to be supplied via Secret Manager only (injecting the
  secret directly rather than via env), so the guard would implicitly be enforced by
  the deployment configuration rather than operator discipline.
- Add a fail-closed post-call check: if `save_request` raises, roll back and exit
  non-zero so the Cloud Run Job reports a task failure rather than success.

For the current scale (one manual session at a time, ~$0.0003/request), the
configuration gate is proportionate. A stronger design is warranted when automated
scheduling is added.

## Critique

- **Good:** The guard is placed before the API key read, so the common
  misconfiguration (no DATABASE_URL in the job) is caught before any network or
  credential access. The error message is actionable and does not echo secrets.
- **Weak:** The guard protects the code path, not the deployed image. The existing
  Cloud Run Job (`app:sha-9cf8ac9`) is still vulnerable until rebuilt and
  redeployed. The step documents this as a known limitation but does not close it.
- **Improve:** Add a Cloud Run Job condition check to `gcloud run jobs describe`
  output in the next deployment step to verify the guard is present in the running
  image before executing any benchmarks.
