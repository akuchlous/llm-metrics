#!/usr/bin/env bash
# Step 023 — bounded 15-minute OpenAI collector, staged. Each stage needs the
# approval named beside it, granted in the executing session. Run one stage
# at a time and inspect its output before the next. Project and region are
# explicit on every command. Nothing here reads a secret payload.
#
# Phase A (Approval A: infrastructure + dry run, NO provider key, NO paid call)
#   apis                 enable Cloud Scheduler API
#   accounts             create SAs llm-metrics-collector, llm-metrics-scheduler
#   grants               collector SA: objectCreator+objectViewer on results
#                        bucket; remove manual job SA's OPENAI_API_KEY access
#   lifecycle            delete attempts/v1/preflight/ objects older than 7 days
#   build                Cloud Build from clean pushed HEAD
#   create-job <digest>  dedicated job, DRY RUN mode, dry policy (current slot)
#   scheduler            */15 UTC trigger, retries 0, created then PAUSED
#   invoker              scheduler SA: roles/run.invoker on the collector job only
#   monitoring <email>   email channel, events metric, 3 alert policies
#   exec-dry             one dry-run execution (job env as configured)
#   exec-expired         one dry-run with an expired policy override
#   exec-alert           one dry-run with an invalid mode override (ERROR)
#   verify               saved job, scheduler, IAM, bucket, policies
#
# Phase B (Approval B: up to 96 paid requests in one 24 h window)
#   activate <START>     START = future UTC quarter-hour "YYYY-MM-DDTHH:MM:SSZ";
#                        collector SA gets OPENAI_API_KEY accessor; job -> prod
#                        mode, policy START..START+24h, key reference attached;
#                        missed-run policy enabled; scheduler resumed
#   stop                 EMERGENCY/after window: pause scheduler, detach key
#                        reference, remove collector SA secret access, disable
#                        missed-run policy (running executions keep their env)
#   audit <START>        mirror claims+records and run collector_audit
#
set -euo pipefail

readonly PROJECT="llm-metrics-513617"
readonly REGION="us-central1"
readonly JOB="llm-metrics-collector"
readonly SCHEDULER_JOB="llm-metrics-collector-15m"
readonly BUCKET="llm-metrics-513617-results"
readonly PREFIX="attempts"
readonly IMAGE_REPO="${REGION}-docker.pkg.dev/${PROJECT}/llm-metrics/app"
readonly COLLECTOR_SA="llm-metrics-collector@${PROJECT}.iam.gserviceaccount.com"
readonly SCHEDULER_SA="llm-metrics-scheduler@${PROJECT}.iam.gserviceaccount.com"
readonly MANUAL_JOB_SA="llm-metrics-job@${PROJECT}.iam.gserviceaccount.com"
readonly BUILD_SA="projects/${PROJECT}/serviceAccounts/llm-metrics-build@${PROJECT}.iam.gserviceaccount.com"
readonly BASE_ENV="LLM_METRICS_ORIGIN_CLOUD=gcp,LLM_METRICS_ORIGIN_REGION=${REGION},LLM_METRICS_RESULTS_BACKEND=gcs,LLM_METRICS_RESULTS_BUCKET=${BUCKET},LLM_METRICS_RESULTS_PREFIX=${PREFIX}"
readonly HERE="$(cd "$(dirname "$0")" && pwd)"

g=(--project="${PROJECT}")
gr=(--project="${PROJECT}" --region="${REGION}")
gl=(--project="${PROJECT}" --location="${REGION}")

plus24h() { date -u -d "$(echo "$1" | sed 's/T/ /; s/Z/ UTC/') + 24 hours" +%Y-%m-%dT%H:%M:%SZ; }
current_slot() {
  local h m
  h=$(date -u +%Y-%m-%dT%H); m=$(date -u +%M)
  printf '%s:%02d:00Z' "${h}" $(( (10#${m} / 15) * 15 ))
}
check_quarter() {
  [[ "$1" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:(00|15|30|45):00Z$ ]] || {
    echo "START must be a UTC quarter-hour YYYY-MM-DDTHH:MM:00Z" >&2; exit 1; }
}
describe_job() {
  gcloud run jobs describe "${JOB}" "${gr[@]}" \
    --format='yaml(spec.template.metadata.annotations,spec.template.spec.taskCount,spec.template.spec.template.spec)'
}
policy_id() {
  gcloud monitoring policies list "${g[@]}" \
    --filter="displayName=\"$1\"" --format='value(name)'
}

case "${1:-}" in
  apis)
    gcloud services enable cloudscheduler.googleapis.com "${g[@]}"
    ;;
  accounts)
    gcloud iam service-accounts create llm-metrics-collector "${g[@]}" \
      --display-name="llm-metrics scheduled collector (runtime)"
    gcloud iam service-accounts create llm-metrics-scheduler "${g[@]}" \
      --display-name="llm-metrics collector scheduler (invoker only)"
    ;;
  grants)
    for role in roles/storage.objectCreator roles/storage.objectViewer; do
      gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" "${g[@]}" \
        --member="serviceAccount:${COLLECTOR_SA}" --role="${role}" --format=none
    done
    # Provider credentials only for the guarded collector: the manual job's
    # SA loses access (it has no key reference attached anyway).
    gcloud secrets remove-iam-policy-binding OPENAI_API_KEY "${g[@]}" \
      --member="serviceAccount:${MANUAL_JOB_SA}" \
      --role=roles/secretmanager.secretAccessor --format=none
    gcloud storage buckets get-iam-policy "gs://${BUCKET}" "${g[@]}" --format='yaml(bindings)'
    gcloud secrets get-iam-policy OPENAI_API_KEY "${g[@]}" --format='yaml(bindings)'
    ;;
  lifecycle)
    gcloud storage buckets update "gs://${BUCKET}" "${g[@]}" \
      --lifecycle-file="${HERE}/023_monitoring/lifecycle.json"
    gcloud storage buckets describe "gs://${BUCKET}" "${g[@]}" --format='yaml(lifecycle_config)'
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
  create-job)
    digest="${2:?usage: create-job sha256:<digest>}"
    [[ "${digest}" =~ ^sha256:[0-9a-f]{64}$ ]] || { echo "bad digest" >&2; exit 1; }
    start="$(current_slot)"
    gcloud run jobs create "${JOB}" "${gr[@]}" \
      --image="${IMAGE_REPO}@${digest}" --service-account="${COLLECTOR_SA}" \
      --tasks=1 --max-retries=0 --task-timeout=180s --cpu=1 --memory=512Mi \
      --set-env-vars="${BASE_ENV},LLM_METRICS_COLLECTOR_MODE=dryrun,LLM_METRICS_COLLECTOR_START=${start},LLM_METRICS_COLLECTOR_EXPIRES=$(plus24h "${start}")" \
      --command=python --args="-m,llm_metrics.scheduled_collector"
    describe_job
    ;;
  scheduler)
    gcloud scheduler jobs create http "${SCHEDULER_JOB}" "${gl[@]}" \
      --schedule="*/15 * * * *" --time-zone="Etc/UTC" \
      --uri="https://run.googleapis.com/v2/projects/${PROJECT}/locations/${REGION}/jobs/${JOB}:run" \
      --http-method=POST --oauth-service-account-email="${SCHEDULER_SA}" \
      --max-retry-attempts=0 --attempt-deadline=180s
    gcloud scheduler jobs pause "${SCHEDULER_JOB}" "${gl[@]}"
    gcloud scheduler jobs describe "${SCHEDULER_JOB}" "${gl[@]}"
    ;;
  invoker)
    gcloud run jobs add-iam-policy-binding "${JOB}" "${gr[@]}" \
      --member="serviceAccount:${SCHEDULER_SA}" --role=roles/run.invoker --format=none
    gcloud run jobs get-iam-policy "${JOB}" "${gr[@]}" --format='yaml(bindings)'
    ;;
  monitoring)
    email="${2:?usage: monitoring <email>}"
    channel="$(gcloud beta monitoring channels create "${g[@]}" --type=email \
      --display-name="llm-metrics collector alerts" \
      --channel-labels="email_address=${email}" --format='value(name)')"
    echo "notification channel: ${channel}"
    gcloud logging metrics create llm_metrics_collector_events "${g[@]}" \
      --description="llm-metrics collector events (any)" \
      --log-filter='resource.type="cloud_run_job" AND resource.labels.job_name="llm-metrics-collector" AND jsonPayload.component="llm-metrics-collector"'
    for f in collector_errors scheduler_errors collector_missed_runs; do
      gcloud monitoring policies create "${g[@]}" \
        --policy-from-file="${HERE}/023_monitoring/${f}.json" \
        --notification-channels="${channel}" --format='value(name,displayName,enabled)'
    done
    ;;
  exec-dry)
    gcloud run jobs execute "${JOB}" "${gr[@]}" --wait || true
    ;;
  exec-expired)
    gcloud run jobs execute "${JOB}" "${gr[@]}" --wait \
      --update-env-vars="LLM_METRICS_COLLECTOR_START=2026-11-01T00:00:00Z,LLM_METRICS_COLLECTOR_EXPIRES=2026-11-02T00:00:00Z" || true
    ;;
  exec-alert)
    gcloud run jobs execute "${JOB}" "${gr[@]}" --wait \
      --update-env-vars="LLM_METRICS_COLLECTOR_MODE=alert-test" || true
    ;;
  verify)
    describe_job
    gcloud run jobs get-iam-policy "${JOB}" "${gr[@]}" --format='yaml(bindings)'
    gcloud scheduler jobs describe "${SCHEDULER_JOB}" "${gl[@]}" \
      --format='yaml(schedule,timeZone,state,retryConfig,attemptDeadline,httpTarget.uri,httpTarget.oauthToken.serviceAccountEmail)'
    gcloud storage buckets describe "gs://${BUCKET}" "${g[@]}" \
      --format='yaml(uniform_bucket_level_access,public_access_prevention,lifecycle_config)'
    gcloud secrets get-iam-policy OPENAI_API_KEY "${g[@]}" --format='yaml(bindings)'
    gcloud monitoring policies list "${g[@]}" --format='table(displayName,enabled)'
    ;;
  activate)
    start="${2:?usage: activate YYYY-MM-DDTHH:MM:00Z}"; check_quarter "${start}"
    expires="$(plus24h "${start}")"
    now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    [[ "${start}" > "${now}" ]] || { echo "START must be in the future" >&2; exit 1; }
    echo "Activating ${start} .. ${expires} (96 slots)"
    gcloud secrets add-iam-policy-binding OPENAI_API_KEY "${g[@]}" \
      --member="serviceAccount:${COLLECTOR_SA}" \
      --role=roles/secretmanager.secretAccessor --format=none
    gcloud run jobs update "${JOB}" "${gr[@]}" \
      --set-env-vars="${BASE_ENV},LLM_METRICS_COLLECTOR_MODE=prod,LLM_METRICS_COLLECTOR_START=${start},LLM_METRICS_COLLECTOR_EXPIRES=${expires}" \
      --set-secrets="OPENAI_API_KEY=OPENAI_API_KEY:latest"
    describe_job
    gcloud monitoring policies update "$(policy_id 'llm-metrics collector: no collector event for 33 minutes (missed slots)')" \
      "${g[@]}" --enabled --format='value(displayName,enabled)'
    gcloud scheduler jobs resume "${SCHEDULER_JOB}" "${gl[@]}"
    gcloud scheduler jobs describe "${SCHEDULER_JOB}" "${gl[@]}" --format='value(state,schedule,timeZone)'
    ;;
  stop)
    gcloud scheduler jobs pause "${SCHEDULER_JOB}" "${gl[@]}" || true
    gcloud run jobs update "${JOB}" "${gr[@]}" --remove-secrets=OPENAI_API_KEY || true
    gcloud secrets remove-iam-policy-binding OPENAI_API_KEY "${g[@]}" \
      --member="serviceAccount:${COLLECTOR_SA}" \
      --role=roles/secretmanager.secretAccessor --format=none || true
    gcloud monitoring policies update "$(policy_id 'llm-metrics collector: no collector event for 33 minutes (missed slots)')" \
      "${g[@]}" --no-enabled --format='value(displayName,enabled)' || true
    gcloud run jobs executions list --job="${JOB}" "${gr[@]}" --limit=3 \
      --format='table(name,createTime,completionTime,runningCount)'
    echo "Running executions keep injected env; cancel with: gcloud run jobs executions cancel <name> ${gr[*]}"
    ;;
  audit)
    start="${2:?usage: audit YYYY-MM-DDTHH:MM:00Z [dryrun]}"; check_quarter "${start}"
    mode="${3:-prod}"
    : "${WORK_DIR:?set WORK_DIR}"; : "${TOOL_IMAGE:?set TOOL_IMAGE (local production image)}"
    rm -rf "${WORK_DIR}/mirror"; mkdir -p "${WORK_DIR}/mirror/${PREFIX}/v1"
    for part in claims requests; do
      gcloud storage cp -r "gs://${BUCKET}/${PREFIX}/v1/${part}" "${WORK_DIR}/mirror/${PREFIX}/v1/" "${g[@]}" 2>/dev/null || true
    done
    docker run --rm --network none -e PYTHONPATH=/app -v "${WORK_DIR}/mirror:/mirror:ro" \
      "${TOOL_IMAGE}" python -m llm_metrics.collector_audit \
      --start "${start}" --expires "$(plus24h "${start}")" --local /mirror --mode "${mode}"
    gcloud run jobs executions list --job="${JOB}" "${gr[@]}" --limit=200 \
      --format='table(name,createTime,succeededCount,failedCount)'
    ;;
  *)
    sed -n '2,32p' "$0"; exit 1
    ;;
esac
