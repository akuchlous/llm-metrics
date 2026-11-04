# Step 018g — Principal engineer

**Step context:** Step 018g is a post-pilot cleanup: five security and operational findings from 018f are addressed — overprivileged IAM, stale secrets, duplicate secret versions, unprotected pilot data, and orphaned build artifacts — without any new database, benchmark run, or API call.

**Question:** The pilot measurement data exists only in a Cloud Shell CSV export. What are the durability properties of Cloud Shell persistent storage, and why is a Cloud Storage backup with SHA-256 checksums the right next step rather than committing the data to git or leaving it in Cloud Shell?

## Answer

Cloud Shell's persistent home directory is a 5 GB network-attached volume per Google account, backed by Cloud Filestore. Google does not publish an SLA for it; the documented risk is that inactive Cloud Shell environments may be reclaimed after 120 days of inactivity, deleting the persistent disk. It is also tied to the Cloud Shell session's Google account; there is no cross-account sharing, and it is not accessible from Cloud Run or other GCP services.

Committing the CSVs to git is wrong for two reasons: the `data/` directory is git-ignored precisely to keep raw measurement data out of version control, and even a CSV could inadvertently contain provider response text or other metadata that should not be in a public (or even private) repository with indefinite retention.

A private Cloud Storage bucket with uniform bucket-level access, no public access, and a retention policy is the correct durability layer: it is durable to multiple nines, accessible from Cloud Run for future import, cheap (~$0.02/GB/month for Standard storage in us-central1), and can be audited independently of the application code. SHA-256 checksums computed before upload and verified by independent download after upload confirm the data was not corrupted in transit and that the stored file matches what was exported from PostgreSQL. The checksums are committed to the git repo as a lightweight, non-secret record of what was archived.

## Critique

- **Good:** Cloud Storage + checksum provides durability, auditability, and a clear restore path without complicating the git history or the application schema.
- **Weak:** A CSV export from PostgreSQL is not a full database backup — it captures the two tables as of the export time but loses index metadata, schema version, and any future rows added before teardown. For a one-row pilot this is acceptable; for a production backup it would not be.
- **Improve:** Store the Alembic revision alongside the CSVs (a one-line text file with the revision hash `f1a2b3c4d5e6`), so a future restore can verify which schema version the data was exported from before running `alembic upgrade head` and importing.
