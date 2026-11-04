# Step 018e — Director

**Step context:** Step 018e is a security/deployability gate before the first cloud deployment. It makes no cloud resource changes, incurs no infrastructure cost, and produces no publishable benchmark data. The Google Cloud project `llm-metrics-513617` is the intended next-step deployment target.

**Question:** Step 018e spends engineering time on security preparation rather than on new measurement capability. How should that choice be evaluated at the product level, and what is the minimum evidence needed before authorizing Step 018f (first cloud deployment)?

## Answer

Cloud deployment enables two outcomes that are currently blocked: (1) automated periodic benchmark runs without a developer's laptop running, and (2) a publicly accessible read-only dashboard that can support user research and growth. Neither is possible from a local machine. The security preparation in Step 018e is the gate that makes those outcomes available safely, not an end in itself.

The business case for the security gate is straightforward: a Cloud Run service with no authentication, an API key in a Docker layer, or a job that can be invoked without `--real` opt-in would create either a security incident or uncontrolled spend before the first benchmark result is published. The cost of the incident would exceed the cost of the gate by multiple orders of magnitude. At the project's current scale ($0.000009 per real request, target $10/day cap, no live users yet), the gate is a one-time investment that unlocks the entire future measurement program.

The minimum evidence for authorizing Step 018f:
1. The Docker image builds and the non-root identity is confirmed (`docker run ... whoami` returns a non-root user).
2. The web service starts and returns HTTP 200 on `/` without any API key set.
3. A local container run confirms no secrets appear in the image layers (`docker history --no-trunc` shows no env vars or build args with credentials).
4. The deployment checklist in `018e-output.md` is reviewed by one other person: IAM, Secret Manager binding, Cloud Run service identity, and migration-before-traffic steps.

## Critique

- **Good:** The step is explicit that it is a gate, not a feature: the "MARKETING CHECKPOINT: not publishable yet" label in the output correctly characterizes the state.
- **Weak:** The authorization criteria for 018f are described in prose; they would be more actionable as a machine-checkable checklist (e.g. a small smoke-test script run against the built image that exits non-zero on failure).
- **Improve:** Add a `scripts/smoke_container.sh` to Step 018f that builds the image and runs the four verification checks above, so "container verified" is a one-command assertion rather than a manual checklist. This also becomes the CI gate for future container changes.
