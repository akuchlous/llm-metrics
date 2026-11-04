# Step 018f — Principal engineer

**Step context:** Step 018f fixes the Docker build-context bug, upgrades Mako for two CVEs, adds offline container-consistency tests, and establishes an explicit authorization gate before any billable GCP action — stopping at a checkpoint with resource names, cost estimates, and a teardown plan.

**Question:** The step uses a two-phase authorization gate: Stage A (free/local) always runs; Stage B (billable) requires explicit in-session user approval. What failure modes does this pattern prevent, and when does it break down?

## Answer

The gate prevents three classes of unintended spend: (1) accidental execution — the prompt being run as a script or autonomously replayed cannot trigger billing without a human reviewing and approving the named resource plan; (2) scope creep — Stage A produces a named list of resources, regions, and cost bounds; approval is specific to that list, so an expanded plan in a later turn is not covered; (3) silent escalation — the commit and stop at the checkpoint ensures there is a natural review point before any state in GCP changes.

The pattern breaks down in several ways. First, if approval is phrased loosely ("go ahead with 018f"), it is ambiguous whether it covers Stage A, Stage B, or both; the prompt requires the approval to be "explicit" and "bounded" but cannot technically verify what the user understood. Second, the gate is enforced by code review and prompt adherence, not by a technical control — there is no IAM deny policy or budget alert that would stop a runaway agent from provisioning resources. Third, the stage boundary is in a markdown file, not in an automated gate; a future agent that runs the same prompt may ignore the stop instruction.

The design is correct for a human-in-the-loop workflow, but should be paired with a GCP budget alert (billable spend > $1/day triggers email) and a one-command teardown that can be run at any point to stop accruing cost.

## Critique

- **Good:** The gate requires explicit, session-specific approval with a named teardown plan — this prevents the class of "it seemed approved" failures.
- **Weak:** The authorization is enforced by a markdown instruction, not a technical control. A budget alert at the GCP project level would add an independent safety net that fires even if the prompt gate is bypassed.
- **Improve:** Add `gcloud billing budgets create` with a $5/month alert as the first billable action in Stage B, before provisioning any database or registry. That way a cost overrun is caught within one billing cycle regardless of what else goes wrong.
