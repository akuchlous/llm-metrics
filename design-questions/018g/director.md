# Step 018g — Director

**Step context:** Step 018g is a five-finding post-pilot security cleanup: overprivileged IAM, stale secrets, duplicate secret versions, unprotected pilot data, and orphaned build artifacts — resolved immediately after the first real cloud measurement.

**Question:** The project has one real benchmark data point and is spending a cleanup step before collecting more. How do you evaluate the credibility cost of skipping this step versus the opportunity cost of doing it?

## Answer

The credibility cost of skipping is asymmetric and compounding. `roles/editor` on the default compute SA means that any build worker or VM can overwrite secrets, delete database instances, or exfiltrate API keys — a single compromised dependency in the build chain could corrupt or destroy the measurement record. If that happened after publishing results, the incident would undermine confidence in every measurement, not just the ones taken after the breach. The stale database URL secret is a smaller but real risk: a future operator reading the Cloud Run Job configuration would see a secret reference to what appears to be an active database and might make decisions based on that assumption.

The opportunity cost is a few hours of engineering time and a 018g step in the prompt history. The project has one data point; it is not publishable yet regardless. The next step (more measurements, additional providers) starts from a materially better security baseline if cleanup is done now.

The strategic argument: the LLM Metrics project's credibility rests on measurement fidelity and reproducibility. Infrastructure hygiene is part of that — a compromised measurement environment produces results that cannot be trusted, and undisclosed security debt is a liability that becomes a headline if discovered externally. Doing the cleanup now, with a committed audit trail, is the right call.

## Critique

- **Good:** The decision to clean up before scaling is the correct tradeoff: the cleanup cost is bounded, the security risk is unbounded, and there is no published result to protect yet.
- **Weak:** A budget alert at $100/month does not auto-suspend resources (D070 notes this). Until programmatic billing suspension is in place, the budget ceiling is advisory only. This is a gap the director should flag: the project relies on manual response to alerts.
- **Improve:** Add a Cloud Billing programmatic notification that disables billing on the project if spend exceeds the threshold. This turns the advisory budget into a hard cap and closes the "alerts notify but don't stop" gap identified in 018g. Cost: free (uses Pub/Sub and a Cloud Function or Eventarc trigger).
