# Step 018g output — Post-pilot security cleanup and durable backup

## Status: COMPLETE — all five findings resolved (2026-11-04)

Executed in Google Cloud Shell (project `llm-metrics-513617`, account = project owner). Phase A was read-only. Phase B mutations were made only after explicit in-session user approval ("aproved for all actions", 2026-11-04). No secret payloads were read, printed or compared. No CSV contents were printed. No new Cloud SQL, no paid OpenAI request, no public service.

---

## Five-finding matrix

| # | Severity | Finding | Baseline (Phase A) | Dependency evidence | Action (approved) | Independent verification | Status |
|---|---|---|---|---|---|---|---|
| 1 | HIGH | Default compute SA has project `roles/editor` | `serviceAccount:578834681009-compute@developer.gserviceaccount.com` bound to `roles/editor` | Only Cloud Run Job runs as `llm-metrics-job@`; no Cloud Run services; only build ran as `llm-metrics-build@`; SA-level IAM policy empty (no one can actAs it) | `gcloud projects remove-iam-policy-binding … --role=roles/editor` | Re-read project IAM: compute SA has **no** project roles; only `roles/owner` (user) remains at editor-or-broader | RESOLVED |
| 2 | MEDIUM | Stale `LLM_METRICS_DATABASE_URL` secret | Secret v1 enabled; job env referenced it (`latest`); job annotation pointed at deleted `llm-metrics-postgres` | `gcloud sql instances list` → 0 instances; only consumer was the job; accessor was only `llm-metrics-job@` | `gcloud run jobs update … --remove-secrets=LLM_METRICS_DATABASE_URL --clear-cloudsql-instances`; then `gcloud secrets delete LLM_METRICS_DATABASE_URL` | Job describe: no DB env, Cloud SQL annotation empty, SA/image/OpenAI ref unchanged; `gcloud secrets list` → only `OPENAI_API_KEY` | RESOLVED |
| 3 | MEDIUM | Duplicate `OPENAI_API_KEY` v1 | v2 enabled (03:36:36Z), v1 enabled (03:36:02Z) | Job references `OPENAI_API_KEY:latest` → v2; nothing pins v1 | `gcloud secrets versions disable 1 --secret=OPENAI_API_KEY` (disabled, **not destroyed**) | v1 `DISABLED`, v2 `ENABLED`; `latest` resolves to v2 | RESOLVED (reversible; destroy deferred) |
| 4 | MEDIUM | Pilot data only in Cloud Shell home | `~/llm-metrics-018f-result/requests.csv` (1 row) and `observations.csv` (4 rows) only copies | Cloud SQL deleted in 018f; no other copy | Created private bucket; uploaded CSVs + `SHA256SUMS` | Independent download to a temp directory; `sha256sum -c` OK for both; row counts match | RESOLVED |
| 5 | LOW | Orphaned Cloud Build source archives | 3 × 492,981 B `.tgz` in `gs://llm-metrics-513617_cloudbuild/source/` | 1 referenced by completed build `2eb2f455…` (SUCCESS, historical); 2 had no build record; no active builds | `gcloud storage rm` of the three tarballs | Bucket now 0 objects; image `app:sha-9cf8ac9` still in Artifact Registry | RESOLVED |

---

## Phase A — Read-only inspection results

- **IAM (editor or broader):** `user:akuchlous@gmail.com` (`roles/owner`), default compute SA (`roles/editor`). Other project bindings: `cloudbuild.builds.builder` (Cloud Build legacy SA), `cloudsql.client` (`llm-metrics-job@`), `logging.logWriter` (`llm-metrics-build@`), and Google-managed service agents.
- **Cloud Run:** one job `llm-metrics-benchmark` (us-central1), SA `llm-metrics-job@`, image `…/llm-metrics/app:sha-9cf8ac9`, literal env `LLM_METRICS_ORIGIN_CLOUD`/`_REGION`, secret env `OPENAI_API_KEY:latest` and `LLM_METRICS_DATABASE_URL:latest`, Cloud SQL annotation to the deleted instance. One execution (`llm-metrics-benchmark-lz969`, 2026-11-04T03:40:14Z, succeeded). No Cloud Run services.
- **Dormancy:** Cloud Scheduler API is not enabled (no schedules); no triggers. The job runs only if manually executed (`gcloud run jobs execute`). Job command: `python -m llm_metrics.real_benchmark --provider openai --real`.
- **Residual risk (found after Phase B):** with `LLM_METRICS_DATABASE_URL` removed, `config.get_database_url()` falls back to SQLite inside the container, so the D068 pre-flight check **passes**. A manual execution would make one paid OpenAI request (~$0.0003) and store it in ephemeral container SQLite, where it is lost on exit. Before 018g the same execution would have failed pre-flight against the deleted Cloud SQL instance. Impact is small (manual action required, sub-cent cost), but it is a silent-data-loss path. Recommended fix (next step, not done here): make `real_benchmark` refuse `--real` when `LLM_METRICS_ORIGIN_CLOUD` is a cloud origin and no `LLM_METRICS_DATABASE_URL` is set; or, until then, do not execute the job.
- **Secrets:** see matrix. Accessor on both secrets: `llm-metrics-job@` only.
- **Cloud Build:** one recorded build `2eb2f455-3700-4852-bf8b-a54d5147a557` (SUCCESS, 03:33:29Z, SA `llm-metrics-build@`). No triggers.
- **Cloud SQL:** 0 instances.
- **Billing:** enabled (billing account linked). Budget alert unchanged from 018f.
- **Pilot CSV integrity** (programmatic check, contents not printed): `requests.csv` 23 columns, 1 data row; `observations.csv` 8 columns, 4 data rows; no ragged rows; no prompt/response/key/password/database-URL column names; no key-like (`sk-…`), `Bearer` or `postgres://` values.

---

## Phase B — Verified private backup (finding 4)

| Property | Value |
|---|---|
| Bucket | `gs://llm-metrics-513617-pilot-backups` |
| Location / class | `US-CENTRAL1`, `STANDARD` |
| Access | uniform bucket-level access **on**; public access prevention **enforced**; only project-role legacy bindings (owner/editor/viewer) |
| Versioning | enabled |
| Prefix | `snapshots/018f/2026-11-04/` |

| Object | Size | Created (UTC) | Rows (data) | SHA-256 |
|---|---|---|---|---|
| `requests.csv` | 583 B | 2026-11-04T05:19:06Z | 1 | `b2735571cfe41f9a7c77410bbcab661ef9aa05d399069ada30b978fdb158b54f` |
| `observations.csv` | 543 B | 2026-11-04T05:19:06Z | 4 | `4eff48f433d27c224ebea216758133d97d163601f3ddc4b655cf18504afdd07a` |
| `SHA256SUMS` | 162 B | 2026-11-04T05:19:05Z | — | (manifest of the two above) |

Source files: exported 2026-11-04T03:43:15Z in 018f. Total stored: 1,288 bytes.

**Restore:**

```bash
mkdir -p ~/restore-018f && cd ~/restore-018f
gcloud storage cp "gs://llm-metrics-513617-pilot-backups/snapshots/018f/2026-11-04/*" .
sha256sum -c SHA256SUMS
```

The CSVs map to the v7 `requests` and observations tables. To reload into a future PostgreSQL database, migrate a fresh DB first (`storage.connect()` → Alembic head), then `\copy requests FROM 'requests.csv' CSV HEADER` followed by observations (FK order).

**Limits:** this is a one-time snapshot of one request and four observations, not a full PostgreSQL backup, and not a recurring storage design. The CSVs are not committed to git.

---

## Re-configuring the job for a future run (finding 2)

The job no longer has a database. Before any future execution:

1. Provision a database (separately approved step).
2. Create a new secret (e.g. `LLM_METRICS_DATABASE_URL`) and grant `roles/secretmanager.secretAccessor` to `llm-metrics-job@`.
3. `gcloud run jobs update llm-metrics-benchmark --region us-central1 --set-secrets=LLM_METRICS_DATABASE_URL=LLM_METRICS_DATABASE_URL:latest --set-cloudsql-instances=<PROJECT:REGION:INSTANCE>`

The job SA still has project `roles/cloudsql.client` (harmless without an instance; kept so future runs need no IAM change — remove it if no DB returns).

---

## Rollback

| # | Rollback |
|---|---|
| 1 | `gcloud projects add-iam-policy-binding llm-metrics-513617 --member=serviceAccount:578834681009-compute@developer.gserviceaccount.com --role=roles/editor` (not recommended) |
| 2 | Secret deleted permanently; recreate per the section above when a DB exists |
| 3 | `gcloud secrets versions enable 1 --secret=OPENAI_API_KEY` |
| 4 | `gcloud storage rm -r gs://llm-metrics-513617-pilot-backups` (would lose the only durable copy) |
| 5 | Not needed; source is git commit `9cf8ac9`, image retained |

---

## GCP resource inventory (post-018g)

| Resource | State |
|---|---|
| Cloud Run Job `llm-metrics-benchmark` (us-central1) | Idle; SA `llm-metrics-job@`; image `app:sha-9cf8ac9`; env: origin literals + `OPENAI_API_KEY:latest` only |
| Cloud Run services | none |
| Cloud SQL | none |
| Secret `OPENAI_API_KEY` | v2 enabled, v1 disabled |
| Artifact Registry `llm-metrics` (us-central1) | image `app:sha-9cf8ac9` |
| Bucket `llm-metrics-513617_cloudbuild` | empty |
| Bucket `llm-metrics-513617-pilot-backups` | 3 objects, 1,288 B, private |
| Service accounts | `llm-metrics-job@`, `llm-metrics-build@`, default compute SA (no project roles) |
| Cloud Scheduler | API not enabled |
| Budget alert | unchanged ($100/month; 50/90/100% notifications) |

---

## Ongoing cost

| Item | Estimate |
|---|---|
| Secret Manager: 2 versions (enabled + disabled count as active versions) | ~$0.12/month |
| Deleted DB secret | −~$0.06/month |
| Backup bucket (1.3 KB Standard) | ~$0.00 |
| Artifact Registry (~67 MB) | free tier / ~$0.01 |
| Cloud Run Job idle | $0 |
| **Total** | **~$0.13/month** (destroying OpenAI v1 later would save ~$0.06) |

No API spend in 018g. Well under the $10/day target. Budget alerts are notifications, not spend caps.

---

## Approval boundary

Phase A checkpoint listed the exact five actions (IAM removal on the default compute SA, job DB-reference removal + secret deletion, disable — not destroy — `OPENAI_API_KEY` v1, private bucket + upload with checksums, deletion of the three named tarballs). The user replied "aproved for all actions". Nothing outside that list was mutated.

**Not changed (recommendation only):** `~/.claude/settings.json` still allows `Bash(gcloud *)`. Recommended: narrow it to read-only patterns (e.g. `gcloud * list`, `gcloud * describe`) so mutations prompt. Left for the operator to decide.

---

## Test evidence

No code changed in 018g, so no tests were required. The offline suite was **not executed** in this step (Cloud Shell has no project venv); the last executed result is inherited from 018e (387 tests: 374 run offline, 13 skipped). `./run.sh` not run.

---

## Limits

- n=1 real measurement; not publishable.
- Backup is a snapshot of two CSVs, not a PostgreSQL dump or recurring backup.
- `OPENAI_API_KEY` v1 is disabled, not destroyed (reversible by design).
- The job is dormant but not fail-closed: a manual execution would spend ~$0.0003 and lose the result to container SQLite (see Phase A residual risk). Do not execute it until the guard or a database exists.
- Bucket uses project-role legacy bindings; anyone with project viewer can read the CSVs (which contain no secrets or prompts).

---

## Design Q&A (concise)

**Q (lead):** Why is `roles/editor` on the default compute SA dangerous and how do you verify removal is safe?
**A:** It grants broad project write access to any workload defaulting to that SA. Verified safe: the job runs as `llm-metrics-job@`, the build ran as `llm-metrics-build@`, there are no services, and no one can act as the compute SA. See `design-questions/018g/lead-engineer.md`.

**Q (principal):** Why is Cloud Storage + SHA-256 checksum the right backup target, not git?
**A:** `data/` is git-ignored; CSVs could contain metadata that should not be in version control. A private, versioned bucket with a checksum manifest is durable, auditable and costs effectively nothing. See `design-questions/018g/principal-engineer.md`.

**Q (manager):** Why clean up before collecting more measurements?
**A:** HIGH/MEDIUM findings compound with every new step, and the only copy of the pilot data was in Cloud Shell, which is reclaimed after inactivity. Cleanup took one session and ~$0. See `design-questions/018g/senior-manager.md`.

**Q (director):** How do you weigh credibility cost vs opportunity cost of this step?
**A:** A compromised project or lost first data point would undermine the measurement record. Opportunity cost was one short step; that risk is now closed. See `design-questions/018g/director.md`.

---

## MARKETING CHECKPOINT

**Not publishable yet.** One real data point. Security cleanup and durable backup are prerequisites for credible future results, not a publishable finding.

---

## Smallest next step

Step 018h: make cloud `--real` runs fail closed without `LLM_METRICS_DATABASE_URL` (residual risk above), add a `cloudbuild.yaml` (D071), and a documented, approval-gated runbook to re-attach a database and execute a small batch of repeated `gpt-6-luna` measurements, with the CSV/backup path made routine — still single provider, no scheduler, no public publishing.
