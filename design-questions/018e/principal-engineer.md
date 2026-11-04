# Step 018e — Principal engineer

**Step context:** Step 018e adds a Dockerfile that uses `python:3.13-slim`, Gunicorn as the WSGI server, a non-root user, and `0.0.0.0:$PORT` binding for Cloud Run. The same image serves both the read-only web service and, with an overridden `CMD`, the one-shot benchmark job.

**Question:** The Dockerfile uses a single image for both the web service and the benchmark job via CMD override. What are the security and operational risks of this design, and what is a safer boundary at scale?

## Answer

The single-image approach minimizes surface area: one image to build, sign, scan, and audit. For the current project (two modes, same codebase, same runtime), it is appropriate. The risks it creates are:

**Security risks:** a single image with both modes means that the Cloud Run service identity (the web service's service account) has the same image as the job runner. If a job identity needs access to the OpenAI API key (via Secret Manager), that secret must not be reachable by the web service's identity. The current design relies on separate Cloud Run service accounts and Secret Manager IAM bindings (documented in the deployment checklist in `018e-output.md`) to enforce the boundary. If the wrong service account is used, the web service would have access to the API key.

**Operational risks:** a CMD override is easy to pass incorrectly. The `--real` flag is the explicit paid-call opt-in, but nothing in the container prevents `docker run <image> python -m llm_metrics.real_benchmark --provider openai --real` from being run as the web service's container by mistake. The `--real` flag is the last line of defense.

A safer boundary at scale would be to build two images from a shared base: a base layer (application code and dependencies) and two derived layers — one with only the web service entrypoint, one with only the job entrypoint — so the web service image cannot run the benchmark command even if its container is compromised.

## Critique

- **Good:** Single-image design is explicitly documented as two modes with clear CMD examples; the web service default makes no paid calls by design. This is appropriate for a development-stage project.
- **Weak:** The design relies entirely on external controls (service accounts, Secret Manager IAM, Cloud Run configuration) to prevent the web service from accessing the OpenAI key. There is no code-level enforcement.
- **Improve:** At scale, split into a `base` + `web` + `job` multi-stage build, and test that the `web` image exits with an error when invoked as a benchmark command. A negative-capability test is more reliable than a policy document.
