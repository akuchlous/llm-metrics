# Step 018g — Lead engineer

**Step context:** Step 018g removes `roles/editor` from the GCP default compute service account, deletes a stale database URL secret, retires a duplicate secret version, backs up the pilot measurement CSVs to private Cloud Storage, and deletes orphaned Cloud Build source archives — without creating any new database or making any paid API call.

**Question:** The default Compute Engine service account was automatically granted `roles/editor` on the project when Cloud Build and Cloud Run APIs were enabled. Why is this dangerous, what does removing it break, and how do you verify nothing depends on it before removing it?

## Answer

`roles/editor` is a primitive IAM role that grants read and write access to almost every GCP API in the project. The default compute SA (`PROJECT_NUMBER-compute@developer.gserviceaccount.com`) is attached to Cloud Build workers by default unless overridden. If Cloud Build runs with this identity, it has write access to Cloud SQL, Secret Manager, Artifact Registry, and every other enabled API — far beyond what a build step needs.

In this project the Cloud Build job explicitly overrides the identity to `llm-metrics-build`, which has only `artifactregistry.writer` on one repo, `logging.logWriter`, and `storage.objectViewer` on the Cloud Build bucket (D071). The Cloud Run Job uses `llm-metrics-job`, which has only `cloudsql.client` and `secretAccessor` on its two secrets. Neither active workload uses the default compute SA.

Before removing `roles/editor`, verify by: (1) listing all Cloud Run services and jobs and checking their `--service-account` field — none should reference the default compute SA; (2) checking the Cloud Build trigger/submit history to confirm all recent builds used `llm-metrics-build`; (3) checking any other resources (GCE VMs, Dataflow, Pub/Sub workers) that might default to this SA — in this project, none of those exist. After removal, re-inspect the IAM policy to confirm the binding is gone, then run a no-op Cloud Build job and confirm it still succeeds under `llm-metrics-build`.

## Critique

- **Good:** The step removes a standing privilege that grants unlimited project write access to any build worker or VM that defaults to the compute SA — a significant attack surface reduction.
- **Weak:** Removing `roles/editor` from the default compute SA does not prevent GCP from re-granting it automatically in some circumstances (e.g. enabling certain APIs). The correct long-term fix is to disable the automatic role grant at the organization level.
- **Improve:** After removal, verify by attempting a no-op operation that would have required `roles/editor` (e.g. trying to list Cloud SQL instances as that SA) and confirming it fails. That closes the verification loop rather than relying only on the IAM policy listing.
