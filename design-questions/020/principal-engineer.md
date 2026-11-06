# Principal engineer — Step 020: guarded second OpenAI cloud pilot

**Step context:** Step 020 replaced the pre-guard Cloud Run Job image with an immutable, digest-pinned build containing the 018h fail-closed cloud-origin database guard, proved the guard in the cloud with the model key detached (exit 2, "No request was made"), then under a separate approval ran exactly one OpenAI `gpt-6-luna` measurement into a temporary Cloud SQL PostgreSQL 17 instance, exported and independently verified a checksummed backup, and tore the database down.

---

## Question

Step 020 stored a measurement by creating Cloud SQL, running one request, exporting CSVs to GCS and deleting the instance. Is this "ephemeral database per measurement" pattern a sound durable-storage design? Where does it fail, and what should replace it?

## Answer

**What it got right for n = 1:**
- Durability came from the *export*, not the database: `snapshots/020/2026-11-06-llm-metrics-benchmark-4mwqz/` holds `requests.csv`, `observations.csv`, `manifest.json` (schema v7, Alembic `f1a2b3c4d5e6`, row counts, column order, CSV hashes, restore recipe) and `SHA256SUMS`. A restore into a fresh PostgreSQL 17 was actually performed and returned the same row.
- Teardown was conditional on independent verification (separate download, `sha256sum -c`, row-count match), so the failure mode "deleted the only copy" was closed.
- Cost: ~18 minutes of `db-f1-micro` ≈ $0.004, versus ~$9–11/month for an always-on instance (D073).

**Where it breaks as volume grows:**
1. **Latency of provisioning:** ~10 minutes to create the instance for a 1m19s job; a recurring collector cannot wait for that each time.
2. **Operational surface per run:** a new password, secret, IAM binding, proxy, migration, export and deletion every time — each a chance to leak or orphan (a forgotten instance ≈ $0.31/day).
3. **Backups as per-run CSV fragments:** fine for archival, poor as a query store; observation ids restart at 1 in every fresh DB, so combining snapshots needs id remapping (request ids are UUID-like and safe; observation integer ids are not globally unique).
4. **No continuity:** each database begins empty, so analytics (percentiles, windows) can only run after manual merges.

**Replacement direction (next step, not implemented):** keep one durable, low-cost store and make the collector append to it — options include a small always-on Cloud SQL with strict budget accounting, or a write-ahead export model (job writes versioned JSON/Parquet objects to GCS directly; a separate step builds static snapshots per D069), which removes the database from the measurement path entirely.

## Critique

**Good:** the design honours "never invent, never lose": NULL stays NULL through CSV, the manifest records provenance, and destruction was gated on proof.

**Weak / missing:** the export format is ad hoc (no schema version beyond "v7" text, no formal spec); observation ids are not globally unique; the restore recipe lives in a JSON string rather than a tested script.

**Stronger:** define a versioned export schema (and test it), use globally unique observation keys or export them as (request_id, metric) pairs, and decide the recurring store before the third measurement rather than repeating this pattern.
