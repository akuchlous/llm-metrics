# Step 018e — Senior manager

**Step context:** Step 018e is a security-focused gate step: it prepares a minimal container, Gunicorn, pre-flight DB check, and harness strengthening without creating any cloud resources or making paid calls. The Docker image build is marked unverified (Docker not available on this machine).

**Question:** The step produces an unverified container build. What does this reveal about the limits of offline security preparation, and what verification must happen before the first cloud deployment in Step 018f?

## Answer

Offline preparation (Dockerfile, .dockerignore, Gunicorn configuration, pre-flight check) can be reviewed, committed, and checked into version control without a Docker daemon. But it cannot prove that:

1. The image actually builds without errors (a syntax error in `CMD`, a missing COPY source, a failed `pip install` inside the build context, or a packaging conflict would only show at build time).
2. The non-root user is correctly applied (a `USER appuser` before a `COPY` with wrong ownership could silently fail to enforce non-root execution).
3. Secret files are excluded from the build context as intended (`.dockerignore` rules are not tested without a real build).
4. The Gunicorn WSGI factory call works at runtime (a Gunicorn startup error only surfaces when the container starts).

The unverified label is not a placeholder to clear later; it is a contract with the reviewer: "this code is mergeable but the container is not ready to deploy." Before Step 018f deploys to Cloud Run, the team must run `docker build`, `docker run --rm -e PORT=8080 <image>`, confirm the web service starts (non-root, responds to requests), and confirm that `--real` is not invoked by the default CMD. Only then can the image hash be pinned for Artifact Registry.

## Critique

- **Good:** Marking the build explicitly unverified is more honest than claiming it is ready; reviewers know what to check in 018f rather than discovering the gap in production.
- **Weak:** The "unverified" label is in the output document, not in the Dockerfile or deployment checklist. A developer picking up 018f could miss it.
- **Improve:** Add a `# UNVERIFIED — build and smoke-test before deploying` comment inside the Dockerfile (above the CMD line) that is removed as part of the 018f verification task, making the unverified state visible in the artifact itself.
