# Lead engineer — Step 020: guarded second OpenAI cloud pilot

**Step context:** Step 020 replaced the pre-guard Cloud Run Job image with an immutable, digest-pinned build containing the 018h fail-closed cloud-origin database guard, proved the guard in the cloud with the model key detached (exit 2, "No request was made"), then under a separate approval ran exactly one OpenAI `gpt-6-luna` measurement into a temporary Cloud SQL PostgreSQL 17 instance, exported and independently verified a checksummed backup, and tore the database down.

---

## Question

The deployed image already contains a guard that refuses cloud-origin runs without PostgreSQL. Why did Phase A *also* detach the `OPENAI_API_KEY` secret reference before deploying and executing, and what exactly does the observed log line prove versus what is inferred?

## Answer

**Two independent barriers.** The negative test was designed so it would spend nothing even if the guard were absent:

1. `remove-key` ran first, while the job still pointed at the old `sha-9cf8ac9` image. From that moment no image — old or new — could read a key.
2. The new digest `sha256:1b67b96f…` was deployed with literal env limited to `LLM_METRICS_ORIGIN_CLOUD=gcp` / `LLM_METRICS_ORIGIN_REGION=us-central1` (`--set-env-vars` replaces all literals), no secrets and `--clear-cloudsql-instances`.

**The log distinguishes the cases.** In `real_benchmark.run()` the order is: origin check → `_check_cloud_db_url()` → read API key → `storage.connect()` preflight → adapter. If the build had packaged pre-guard code, the run would still exit 2 but print `OPENAI_API_KEY is not set`. The execution `llm-metrics-benchmark-q9nlr` printed `LLM_METRICS_DATABASE_URL is not set or is empty … require an explicit PostgreSQL … No request was made.`, which only the guard emits. So:

- **Observed:** the deployed digest contains the guard and it fired; exit code 2; one task, no retry; no key attached.
- **Inferred from code + the local image smoke:** the refusal happened before any key read or network access. Cloud Run's "failed" state alone proves nothing about provider calls.

**Deploy by digest, not tag.** `--image=…/app@sha256:…` means the job cannot drift if someone re-pushes `sha-0ce36df`; the execution record shows the same digest.

## Critique

**Good:** defence in depth costs one extra `gcloud run jobs update`; the expected message was predicted before execution, so the test could fail meaningfully; the old image was never executed.

**Weak / missing:** there is no automated test that the *deployed* image's guard message matches the source (the check was a human reading logs). The `sha-0ce36df` tag is still mutable in Artifact Registry; immutable tags are not enabled on the repository.

**Stronger:** have `020_phase_a.sh execute` grep the execution logs for the exact guard string and fail loudly otherwise; enable Artifact Registry immutable tags; add a CI check that builds the production image and runs the gcp/no-DB smoke so the property is verified on every commit, not per pilot.
