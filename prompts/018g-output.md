# Step 018g output — Post-pilot security cleanup and durable backup

## Status: BLOCKED PENDING CLOUD SHELL EXECUTION

Phase A (read-only inspection) and Phase B (five findings) must be executed from Google Cloud Shell. This file will be updated with verified results once Cloud Shell execution completes.

The design questions, README update, and this placeholder are committed locally. The cloud-dependent sections below will be filled in after Cloud Shell execution and user approval.

---

## Five-finding matrix

| # | Severity | Finding | Baseline | Action | Verified | Status |
|---|---|---|---|---|---|---|
| 1 | HIGH | Default compute SA has `roles/editor` | TBD | TBD | TBD | PENDING |
| 2 | MEDIUM | Stale `LLM_METRICS_DATABASE_URL` secret | TBD | TBD | TBD | PENDING |
| 3 | MEDIUM | Duplicate `OPENAI_API_KEY` version 1 | TBD | TBD | TBD | PENDING |
| 4 | MEDIUM | Pilot data only in Cloud Shell persistent home | TBD | TBD | TBD | PENDING |
| 5 | LOW | Orphaned Cloud Build source archives | TBD | TBD | TBD | PENDING |

---

## Phase A — Read-only inspection results

*To be filled after Cloud Shell execution.*

---

## Phase B — Actions taken

*To be filled after user approval and Cloud Shell execution.*

---

## GCP resource inventory (post-018g)

*To be filled after Cloud Shell execution.*

---

## Ongoing cost

*To be filled after Cloud Shell execution.*

---

## Test evidence

*To be filled after Cloud Shell execution.*

---

## Design Q&A (concise)

**Q (lead):** Why is `roles/editor` on the default compute SA dangerous and how do you verify removal is safe?
**A:** It grants unlimited project write access to any build worker defaulting to that SA. Verify by checking all Cloud Run and Cloud Build identities first; none in this project use the default SA. See `design-questions/018g/lead-engineer.md`.

**Q (principal):** Why is Cloud Storage + SHA-256 checksum the right backup target, not git?
**A:** `data/` is git-ignored; CSVs could contain metadata that should not be in version control. Cloud Storage is durable, auditable, cheap, and accessible from Cloud Run. See `design-questions/018g/principal-engineer.md`.

**Q (manager):** Why clean up before collecting more measurements?
**A:** HIGH/MEDIUM findings persist and compound with every new step. Cleanup cost is low now; the pilot data could be lost if Cloud Shell is reclaimed before backup. See `design-questions/018g/senior-manager.md`.

**Q (director):** How do you weigh credibility cost vs opportunity cost of this step?
**A:** Skipping risks infrastructure compromise that would corrupt the measurement record and undermine published results. Opportunity cost is bounded; risk is not. See `design-questions/018g/director.md`.

---

## MARKETING CHECKPOINT

**Not publishable yet.** One real data point. Security cleanup and durable backup are prerequisites for credible future results, not a publishable finding.

---

## Smallest next step

*To be determined after Phase B completes. Candidate: Step 018h — second real measurement or additional provider.*
