#!/usr/bin/env bash
# Step 022 — GCS-backed OpenAI pilot, staged. Each stage needs the approval
# named beside it, granted in the executing session. Run one stage at a time
# and inspect its output before the next.
#
# Phase A (Approval A: storage only, NO provider key, NO paid request)
#   bucket            create private results bucket (UBLA, PAP enforced)
#   grant             job SA: objectCreator + objectViewer on that bucket only
#   build             Cloud Build from clean pushed HEAD (cloudbuild.yaml)
#   deploy <digest>   job -> digest, GCS env, storage-smoke command, no secrets
#   verify            print saved job spec
#   execute           run the job ONCE (storage smoke as the job SA)
#   logs <execution>  sanitized job output
#   check             operator-side listing; nothing under requests/prod/
#   fetch <name>      download one object to $WORK_DIR for validation
#
# Phase B (Approval B: exactly ONE paid OpenAI request)
#   paid-config       command -> real_benchmark --real, attach OPENAI_API_KEY ref
#   execute           run the job ONCE; never re-run
#   detach            remove OPENAI_API_KEY ref (always, success or failure)
#
# No Cloud SQL, database secret, scheduler or IAM beyond the bucket grant.
# Project and region are explicit on every command.
set -euo pipefail

readonly PROJECT="llm-metrics-513617"
readonly REGION="us-central1"
readonly JOB="llm-metrics-benchmark"
readonly BUCKET="llm-metrics-513617-results"
readonly PREFIX="attempts"
readonly IMAGE_REPO="${REGION}-docker.pkg.dev/${PROJECT}/llm-metrics/app"
readonly JOB_SA="llm-metrics-job@${PROJECT}.iam.gserviceaccount.com"
readonly BUILD_SA="projects/${PROJECT}/serviceAccounts/llm-metrics-build@${PROJECT}.iam.gserviceaccount.com"
readonly ENV_VARS="LLM_METRICS_ORIGIN_CLOUD=gcp,LLM_METRICS_ORIGIN_REGION=${REGION},LLM_METRICS_RESULTS_BACKEND=gcs,LLM_METRICS_RESULTS_BUCKET=${BUCKET},LLM_METRICS_RESULTS_PREFIX=${PREFIX}"
readonly SMOKE_ARGS="-m,llm_metrics.gcs_smoke"
readonly PAID_ARGS="-m,llm_metrics.real_benchmark,--provider,openai,--real,--workload,interactive-chat-v1"

g=(--project="${PROJECT}")
gr=(--project="${PROJECT}" --region="${REGION}")

describe_job() {
  gcloud run jobs describe "${JOB}" "${gr[@]}" \
    --format='yaml(spec.template.metadata.annotations,spec.template.spec.taskCount,spec.template.spec.template.spec)'
}

case "${1:-}" in
  bucket)
    gcloud storage buckets create "gs://${BUCKET}" "${g[@]}" \
      --location="${REGION}" --default-storage-class=STANDARD \
      --uniform-bucket-level-access --public-access-prevention
    gcloud storage buckets describe "gs://${BUCKET}" "${g[@]}" \
      --format='yaml(location,storage_class,uniform_bucket_level_access,public_access_prevention,versioning_enabled,soft_delete_policy,retention_policy)'
    ;;
  grant)
    for role in roles/storage.objectCreator roles/storage.objectViewer; do
      gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" "${g[@]}" \
        --member="serviceAccount:${JOB_SA}" --role="${role}" --format='none'
    done
    gcloud storage buckets get-iam-policy "gs://${BUCKET}" "${g[@]}" --format='yaml(bindings)'
    ;;
  build)
    git fetch -q origin main
    [[ -z "$(git status --porcelain)" ]] || { echo "dirty tree" >&2; exit 1; }
    [[ "$(git rev-parse HEAD)" == "$(git rev-parse origin/main)" ]] || { echo "HEAD != origin/main" >&2; exit 1; }
    tag="sha-$(git rev-parse --short=7 HEAD)"
    echo "Building ${IMAGE_REPO}:${tag} from $(git rev-parse HEAD)"
    gcloud builds submit "${gr[@]}" --config=cloudbuild.yaml \
      --service-account="${BUILD_SA}" --substitutions="_IMAGE_TAG=${tag}"
    gcloud artifacts docker images describe "${IMAGE_REPO}:${tag}" "${g[@]}" \
      --format='value(image_summary.digest)'
    ;;
  deploy)
    digest="${2:?usage: deploy sha256:<digest>}"
    [[ "${digest}" =~ ^sha256:[0-9a-f]{64}$ ]] || { echo "bad digest" >&2; exit 1; }
    gcloud run jobs update "${JOB}" "${gr[@]}" \
      --image="${IMAGE_REPO}@${digest}" --service-account="${JOB_SA}" \
      --tasks=1 --max-retries=0 --task-timeout=180s \
      --set-env-vars="${ENV_VARS}" --clear-cloudsql-instances \
      --command=python --args="${SMOKE_ARGS}"
    describe_job
    ;;
  verify)
    describe_job
    ;;
  execute)
    gcloud run jobs execute "${JOB}" "${gr[@]}" --wait || true
    gcloud run jobs executions list --job="${JOB}" "${gr[@]}" --limit=1 \
      --format='table(name,createTime,completionTime,succeededCount,failedCount)'
    ;;
  logs)
    execution="${2:?usage: logs <execution-name>}"
    gcloud logging read "${g[@]}" --freshness=2h --order=asc \
      "resource.type=\"cloud_run_job\" AND resource.labels.job_name=\"${JOB}\" AND labels.\"run.googleapis.com/execution_name\"=\"${execution}\"" \
      --format='value(timestamp,severity,textPayload)'
    ;;
  check)
    gcloud storage ls -l -r "gs://${BUCKET}/${PREFIX}/" "${g[@]}" || true
    echo "--- prod namespace (must be empty in Phase A):"
    gcloud storage ls "gs://${BUCKET}/${PREFIX}/v1/requests/prod/" "${g[@]}" 2>&1 || true
    ;;
  fetch)
    name="${2:?usage: fetch <object-name>}"
    : "${WORK_DIR:?set WORK_DIR}"
    mkdir -p "${WORK_DIR}"
    gcloud storage cp "gs://${BUCKET}/${name}" "${WORK_DIR}/" "${g[@]}"
    ;;
  paid-config)
    gcloud run jobs update "${JOB}" "${gr[@]}" \
      --set-env-vars="${ENV_VARS}" --clear-cloudsql-instances \
      --command=python --args="${PAID_ARGS}" \
      --set-secrets="OPENAI_API_KEY=OPENAI_API_KEY:latest"
    describe_job
    ;;
  detach)
    gcloud run jobs update "${JOB}" "${gr[@]}" --remove-secrets=OPENAI_API_KEY
    describe_job
    ;;
  *)
    sed -n '2,24p' "$0"; exit 1
    ;;
esac
