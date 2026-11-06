#!/usr/bin/env bash
# Step 020 Phase A — guarded image deployment and ONE negative execution.
#
# Requires explicit Approval A in the executing session. Run one stage at a
# time and inspect its output before the next:
#
#   bash scripts/gcp/020_phase_a.sh remove-key   # detach OPENAI_API_KEY ref (secret kept)
#   bash scripts/gcp/020_phase_a.sh build        # Cloud Build -> immutable sha tag
#   bash scripts/gcp/020_phase_a.sh deploy <sha256:digest>
#   bash scripts/gcp/020_phase_a.sh verify       # saved spec; must show no secrets
#   bash scripts/gcp/020_phase_a.sh execute      # exactly once; expected exit 2
#   bash scripts/gcp/020_phase_a.sh logs <execution-name>
#
# No stage provisions a database, reads a secret payload, or restores a model
# key. Project and region are explicit on every command.
set -euo pipefail

readonly PROJECT="llm-metrics-513617"
readonly REGION="us-central1"
readonly JOB="llm-metrics-benchmark"
readonly IMAGE_REPO="${REGION}-docker.pkg.dev/${PROJECT}/llm-metrics/app"
readonly JOB_SA="llm-metrics-job@${PROJECT}.iam.gserviceaccount.com"
readonly BUILD_SA="projects/${PROJECT}/serviceAccounts/llm-metrics-build@${PROJECT}.iam.gserviceaccount.com"
# Exact benchmark identity; the image's target registry fixes model and profile
# (openai -> gpt-6-luna / openai.gpt-6-luna.v1).
readonly JOB_ARGS="-m,llm_metrics.real_benchmark,--provider,openai,--real,--workload,interactive-chat-v1"

job_flags=(--project="${PROJECT}" --region="${REGION}")

require_clean_main() {
  git fetch -q origin main
  if [[ -n "$(git status --porcelain)" ]]; then
    echo "Refusing: working tree is dirty." >&2; exit 1
  fi
  if [[ "$(git rev-parse HEAD)" != "$(git rev-parse origin/main)" ]]; then
    echo "Refusing: HEAD is not origin/main (push first)." >&2; exit 1
  fi
}

case "${1:-}" in
  remove-key)
    gcloud run jobs update "${JOB}" "${job_flags[@]}" --remove-secrets=OPENAI_API_KEY
    ;;
  build)
    require_clean_main
    tag="sha-$(git rev-parse --short=7 HEAD)"
    echo "Building ${IMAGE_REPO}:${tag} from $(git rev-parse HEAD)"
    gcloud builds submit --project="${PROJECT}" --region="${REGION}" \
      --config=cloudbuild.yaml --service-account="${BUILD_SA}" \
      --substitutions="_IMAGE_TAG=${tag}"
    gcloud artifacts docker images describe "${IMAGE_REPO}:${tag}" \
      --project="${PROJECT}" --format='value(image_summary.digest)'
    ;;
  deploy)
    digest="${2:?usage: deploy sha256:<digest>}"
    [[ "${digest}" =~ ^sha256:[0-9a-f]{64}$ ]] || { echo "bad digest" >&2; exit 1; }
    # --set-env-vars replaces all literal env vars, so no stray DB URL or key
    # can survive; secrets were already removed by the remove-key stage.
    gcloud run jobs update "${JOB}" "${job_flags[@]}" \
      --image="${IMAGE_REPO}@${digest}" \
      --service-account="${JOB_SA}" \
      --tasks=1 --max-retries=0 --task-timeout=180s \
      --set-env-vars=LLM_METRICS_ORIGIN_CLOUD=gcp,LLM_METRICS_ORIGIN_REGION=us-central1 \
      --clear-cloudsql-instances \
      --command=python --args="${JOB_ARGS}"
    ;;
  verify)
    gcloud run jobs describe "${JOB}" "${job_flags[@]}" \
      --format='yaml(spec.template.metadata.annotations,spec.template.spec.taskCount,spec.template.spec.template.spec)'
    ;;
  execute)
    # Expected to FAIL with exit 2 (guard refusal); --wait returns non-zero.
    gcloud run jobs execute "${JOB}" "${job_flags[@]}" --wait || true
    gcloud run jobs executions list --job="${JOB}" "${job_flags[@]}" --limit=1 \
      --format='table(name,createTime,completionTime,succeededCount,failedCount)'
    ;;
  logs)
    execution="${2:?usage: logs <execution-name>}"
    gcloud logging read --project="${PROJECT}" --freshness=1h --order=asc \
      "resource.type=\"cloud_run_job\" AND resource.labels.job_name=\"${JOB}\" AND labels.\"run.googleapis.com/execution_name\"=\"${execution}\"" \
      --format='value(timestamp,severity,textPayload)'
    ;;
  *)
    sed -n '2,15p' "$0"; exit 1
    ;;
esac
