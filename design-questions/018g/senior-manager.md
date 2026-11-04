# Step 018g — Senior manager

**Step context:** Step 018g resolves five post-pilot findings — an overprivileged service account, stale and duplicate secrets, unprotected pilot data, and orphaned build artifacts — immediately after the first successful cloud measurement.

**Question:** The team is doing a cleanup step immediately after the pilot rather than moving straight to the next feature. What is the operational case for this sequencing, and what would be the risk of deferring these findings to a later step?

## Answer

The findings from 018f are not cosmetic: one is HIGH (unrestricted project write access via the default compute SA), two are MEDIUM (a stale secret that could be confused for an active credential, and a duplicate key version that doubles the secret's attack surface). Deferring them means these risks persist for every subsequent step, including the next benchmark run, any new provider, and any future team member who reads the IAM policy. The cleanup cost is low now — no new infrastructure, no schema changes — and grows with every step that layers more resources on top.

The pilot data risk is also time-sensitive: Cloud Shell persistent storage is not backed by an SLA and can be reclaimed. If the team defers the backup until after the next benchmark run, the pilot sample could be lost and the first real measurement would be unrecoverable.

Sequencing cleanup immediately after the pilot also establishes a pattern: every milestone ends with a verified, committed audit of what was created, what was cleaned up, and what the ongoing cost is. That pattern keeps the project auditable and prevents infrastructure debt from accumulating over time.

## Critique

- **Good:** Fixing HIGH and MEDIUM findings before the next run means the security baseline improves monotonically — the next step starts from a known-good state, not a known-bad one.
- **Weak:** A cleanup step does not deliver user-visible progress. For a solo or very small team this is fine; for a larger team it may create pressure to skip it in favor of shipping features, especially if the findings are perceived as theoretical.
- **Improve:** Make the cleanup reviewable at the same level as a feature step — a committed output report with a five-item matrix, independent verification of each action, and a marketing checkpoint. That is exactly what 018g requires, and it sets a precedent that security hygiene is a first-class deliverable, not a footnote.
