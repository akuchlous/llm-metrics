#!/usr/bin/env bash
# Step 020 Phase 0 — READ-ONLY GCP inventory for the guarded second pilot.
#
# Run in Google Cloud Shell from a clean clone of main:
#   bash scripts/gcp/020_inventory.sh 2>&1 | tee ~/020-inventory.txt
#
# Every command is a list/describe/get-iam-policy call: no resource is created,
# changed or executed, and no secret payload is read (only secret metadata).
# Project and region are passed explicitly on every command rather than relying
# on the active gcloud configuration.
set -uo pipefail

readonly PROJECT="llm-metrics-513617"
readonly REGION="us-central1"
readonly JOB="llm-metrics-benchmark"
readonly REPO="llm-metrics"
readonly BACKUP_BUCKET="gs://llm-metrics-513617-pilot-backups"
readonly JOB_SA="llm-metrics-job@${PROJECT}.iam.gserviceaccount.com"
readonly BUILD_SA="llm-metrics-build@${PROJECT}.iam.gserviceaccount.com"

section() { printf '\n===== %s =====\n' "$*"; }
run() { printf '$ %s\n' "$*"; "$@" || printf '(exit %s)\n' "$?"; }

section "Identity and target"
run gcloud config get-value account
echo "PROJECT=${PROJECT} REGION=${REGION}"
run gcloud projects describe "${PROJECT}" --format='value(projectId,projectNumber,lifecycleState)'
run gcloud billing projects describe "${PROJECT}" --format='value(billingEnabled)'
echo "git HEAD: $(git rev-parse HEAD 2>/dev/null) dirty=$(git status --porcelain 2>/dev/null | wc -l)"

section "Cloud Run Job spec (secret references are names only, never values)"
run gcloud run jobs describe "${JOB}" --project="${PROJECT}" --region="${REGION}" \
  --format='yaml(metadata.name,metadata.annotations,spec.template.metadata.annotations,spec.template.spec.taskCount,spec.template.spec.template.spec.maxRetries,spec.template.spec.template.spec.timeoutSeconds,spec.template.spec.template.spec.serviceAccountName,spec.template.spec.template.spec.containers)'
run gcloud run jobs executions list --job="${JOB}" --project="${PROJECT}" --region="${REGION}" \
  --format='table(name,createTime,completionTime,succeededCount,failedCount)'
run gcloud run services list --project="${PROJECT}" --region="${REGION}"

section "Artifact Registry images (tags and digests)"
run gcloud artifacts docker images list "${REGION}-docker.pkg.dev/${PROJECT}/${REPO}/app" \
  --project="${PROJECT}" --include-tags --format='table(digest,tags,createTime,updateTime)'

section "Cloud SQL (expected: none)"
run gcloud sql instances list --project="${PROJECT}"

section "Scheduler (expected: API disabled / no jobs)"
run gcloud services list --enabled --project="${PROJECT}" --format='value(config.name)'
if gcloud services list --enabled --project="${PROJECT}" --format='value(config.name)' \
    | grep -q '^cloudscheduler.googleapis.com$'; then
  run gcloud scheduler jobs list --project="${PROJECT}" --location="${REGION}"
else
  echo "cloudscheduler.googleapis.com not enabled -> no schedules"
fi

section "Secret Manager metadata (no payloads)"
run gcloud secrets list --project="${PROJECT}" --format='table(name,createTime,replication.automatic)'
for secret in $(gcloud secrets list --project="${PROJECT}" --format='value(name.basename())'); do
  run gcloud secrets versions list "${secret}" --project="${PROJECT}" --format='table(name,state,createTime)'
  run gcloud secrets get-iam-policy "${secret}" --project="${PROJECT}" --format='yaml(bindings)'
done

section "Backup bucket (018f snapshot must stay intact)"
run gcloud storage buckets describe "${BACKUP_BUCKET}" --project="${PROJECT}" \
  --format='yaml(location,storage_class,versioning_enabled,public_access_prevention,uniform_bucket_level_access)'
run gcloud storage ls -l -r "${BACKUP_BUCKET}/snapshots/"

section "Cloud Build history and build service account"
run gcloud builds list --project="${PROJECT}" --limit=5 \
  --format='table(id,status,createTime,serviceAccount,options.logging)'
run gcloud builds list --project="${PROJECT}" --region="${REGION}" --limit=5 \
  --format='table(id,status,createTime,serviceAccount,options.logging)'
run gcloud artifacts repositories get-iam-policy "${REPO}" --project="${PROJECT}" \
  --location="${REGION}" --format='yaml(bindings)'
run gcloud storage buckets get-iam-policy "gs://${PROJECT}_cloudbuild" --project="${PROJECT}" \
  --format='yaml(bindings)'

section "Project IAM roles for the job and build service accounts"
run gcloud projects get-iam-policy "${PROJECT}" --flatten='bindings[].members' \
  --filter="bindings.members:(${JOB_SA} OR ${BUILD_SA})" --format='table(bindings.role,bindings.members)'
run gcloud iam service-accounts get-iam-policy "${BUILD_SA}" --project="${PROJECT}" --format='yaml(bindings)'
run gcloud iam service-accounts get-iam-policy "${JOB_SA}" --project="${PROJECT}" --format='yaml(bindings)'

section "Done (read-only)"
