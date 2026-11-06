#!/usr/bin/env bash
# Step 020 Phase B — ONE paid OpenAI measurement with temporary Cloud SQL.
#
# Requires separate explicit Approval B in the executing session. Run one
# stage at a time and inspect output before continuing:
#
#   preflight     job has no schedule, 1 task, 0 retries, nothing running
#   create-sql    temporary zonal PG17 instance (no backups, no networks)
#   create-db     database, app user (password from a 0600 file), URL secret
#   proxy-up      local Cloud SQL Auth Proxy container (token via env only)
#   migrate       Alembic head via storage.connect(); expect 0 rows
#   attach        mount instance + DB secret + restore OPENAI_API_KEY ref
#   execute       the ONE paid execution (no retry, even on failure)
#   verify        sanitized rows from PostgreSQL (before teardown)
#   export <run-id>   CSV + manifest + SHA256SUMS to a new immutable prefix
#   check-backup <run-id>  independent download, sha256sum -c, row counts
#   detach        remove key + DB refs and Cloud SQL mount from the job
#   teardown      delete instance (no final backup), DB secret, local creds
#
# Secret material lives only in $SECRET_DIR files (mode 0600/0700) and the
# Secret Manager secret; it is never echoed, logged or passed as an argv
# value. Project and region are explicit on every gcloud command.
set -euo pipefail

readonly PROJECT="llm-metrics-513617"
readonly REGION="us-central1"
readonly JOB="llm-metrics-benchmark"
readonly INSTANCE="llm-metrics-pg-020"
readonly CONNECTION="${PROJECT}:${REGION}:${INSTANCE}"
readonly DB_NAME="llm_metrics"
readonly DB_USER="llm_metrics_app"
readonly DB_SECRET="LLM_METRICS_DATABASE_URL"
readonly JOB_SA="llm-metrics-job@${PROJECT}.iam.gserviceaccount.com"
readonly BUCKET="gs://llm-metrics-513617-pilot-backups"
readonly PROXY_IMAGE="gcr.io/cloud-sql-connectors/cloud-sql-proxy:2.14.1"
readonly NET="llm-metrics-020"
: "${SECRET_DIR:?set SECRET_DIR to a private directory outside the repo}"
: "${TOOL_IMAGE:?set TOOL_IMAGE to the locally built production image}"
: "${WORK_DIR:?set WORK_DIR to a scratch directory for exports}"

g=(--project="${PROJECT}")
gr=(--project="${PROJECT}" --region="${REGION}")

db_tool() {
  docker run --rm --network "${NET}" -e PYTHONPATH=/app \
    -v "${SECRET_DIR}:/secret:ro" -v "$(pwd)/scripts/gcp:/tools:ro" \
    -v "${WORK_DIR}/out:/out" "${TOOL_IMAGE}" python /tools/020_db_tool.py "$@"
}

case "${1:-}" in
  preflight)
    gcloud services list --enabled "${g[@]}" --format='value(config.name)' \
      | grep -q '^cloudscheduler.googleapis.com$' && echo "SCHEDULER ENABLED" || echo "scheduler API disabled"
    gcloud run jobs describe "${JOB}" "${gr[@]}" --format='value(spec.template.spec.taskCount,spec.template.spec.template.spec.maxRetries,spec.template.spec.template.spec.containers[0].image)'
    gcloud run jobs executions list --job="${JOB}" "${gr[@]}" --format='table(name,createTime,completionTime,runningCount)'
    gcloud sql instances list "${g[@]}"
    ;;
  create-sql)
    gcloud sql instances create "${INSTANCE}" "${g[@]}" --region="${REGION}" \
      --database-version=POSTGRES_17 --edition=enterprise --tier=db-f1-micro \
      --availability-type=zonal --storage-type=SSD --storage-size=10 \
      --no-storage-auto-increase --no-backup --no-deletion-protection \
      --no-retain-backups-on-delete --no-final-backup
    gcloud sql instances describe "${INSTANCE}" "${g[@]}" \
      --format='yaml(state,databaseVersion,region,gceZone,settings.tier,settings.edition,settings.availabilityType,settings.dataDiskSizeGb,settings.backupConfiguration.enabled,settings.ipConfiguration.authorizedNetworks,settings.ipConfiguration.ipv4Enabled)'
    ;;
  create-db)
    umask 077
    install -d -m 700 "${SECRET_DIR}"
    printf '%s' "${DB_USER}" > "${SECRET_DIR}/db_user"
    printf '%s' "${DB_NAME}" > "${SECRET_DIR}/db_name"
    python3 -c 'import secrets; print(secrets.token_hex(32), end="")' > "${SECRET_DIR}/db_password"
    # Password reaches gcloud through a flags file, not argv or shell history.
    python3 - "${SECRET_DIR}" <<'PY'
import json, pathlib, sys
d = pathlib.Path(sys.argv[1])
(d / "user_flags.yaml").write_text(json.dumps({"--password": (d / "db_password").read_text()}))
PY
    gcloud sql databases create "${DB_NAME}" --instance="${INSTANCE}" "${g[@]}"
    gcloud sql users create "${DB_USER}" --instance="${INSTANCE}" "${g[@]}" \
      --flags-file="${SECRET_DIR}/user_flags.yaml"
    rm -f "${SECRET_DIR}/user_flags.yaml"
    # Unix-socket URL used by the Cloud Run Job's Cloud SQL mount (hex password
    # needs no escaping). Piped to Secret Manager via stdin.
    printf 'postgresql+psycopg2://%s:%s@/%s?host=/cloudsql/%s' "${DB_USER}" \
      "$(cat "${SECRET_DIR}/db_password")" "${DB_NAME}" "${CONNECTION}" \
      | gcloud secrets create "${DB_SECRET}" "${g[@]}" --replication-policy=automatic --data-file=-
    gcloud secrets add-iam-policy-binding "${DB_SECRET}" "${g[@]}" \
      --member="serviceAccount:${JOB_SA}" --role=roles/secretmanager.secretAccessor \
      --format='yaml(bindings)'
    ;;
  proxy-up)
    docker network inspect "${NET}" >/dev/null 2>&1 || docker network create "${NET}" >/dev/null
    # Short-lived user access token passed via environment, never argv.
    CSQL_PROXY_TOKEN="$(gcloud auth print-access-token)" \
      docker run -d --name proxy --network "${NET}" -e CSQL_PROXY_TOKEN \
      "${PROXY_IMAGE}" --address 0.0.0.0 --port 5432 "${CONNECTION}" >/dev/null
    sleep 5; docker logs proxy 2>&1 | tail -3
    ;;
  migrate)
    mkdir -p "${WORK_DIR}/out"
    db_tool migrate
    ;;
  attach)
    gcloud run jobs update "${JOB}" "${gr[@]}" \
      --set-cloudsql-instances="${CONNECTION}" \
      --set-secrets="${DB_SECRET}=${DB_SECRET}:latest,OPENAI_API_KEY=OPENAI_API_KEY:latest"
    gcloud run jobs describe "${JOB}" "${gr[@]}" \
      --format='yaml(spec.template.metadata.annotations,spec.template.spec.taskCount,spec.template.spec.template.spec)'
    ;;
  execute)
    # Exactly once. Never re-run automatically, whatever the outcome.
    gcloud run jobs execute "${JOB}" "${gr[@]}" --wait || true
    gcloud run jobs executions list --job="${JOB}" "${gr[@]}" --limit=1 \
      --format='table(name,createTime,completionTime,succeededCount,failedCount)'
    ;;
  verify)
    db_tool verify
    ;;
  export)
    run_id="${2:?usage: export <run-id>}"
    prefix="${BUCKET}/snapshots/020/${run_id}/"
    if gcloud storage ls "${g[@]}" "${prefix}" >/dev/null 2>&1; then
      echo "Refusing: ${prefix} already exists" >&2; exit 1
    fi
    rm -rf "${WORK_DIR}/out"; mkdir -p "${WORK_DIR}/out"
    db_tool export --run-id "${run_id}"
    (cd "${WORK_DIR}/out" && sha256sum requests.csv observations.csv manifest.json > SHA256SUMS && cat SHA256SUMS)
    gcloud storage cp "${g[@]}" --no-clobber "${WORK_DIR}/out/"* "${prefix}"
    gcloud storage ls -l "${g[@]}" "${prefix}"
    ;;
  check-backup)
    run_id="${2:?usage: check-backup <run-id>}"
    check="${WORK_DIR}/check-${run_id}"
    rm -rf "${check}"; mkdir -p "${check}"
    gcloud storage cp "${g[@]}" "${BUCKET}/snapshots/020/${run_id}/*" "${check}/"
    (cd "${check}" && sha256sum -c SHA256SUMS && python3 - <<'PY'
import csv, json
m = json.load(open("manifest.json"))
counts = {t: sum(1 for _ in csv.DictReader(open(f"{t}.csv"))) for t in ("requests", "observations")}
print("row counts", counts, "manifest", m["row_counts"], "MATCH" if counts == m["row_counts"] else "MISMATCH")
for t in ("requests", "observations"):
  sha = __import__("hashlib").sha256(open(f"{t}.csv", "rb").read()).hexdigest()
  print(t, "manifest sha", "MATCH" if sha == m["sha256"][f"{t}.csv"] else "MISMATCH")
PY
)
    gcloud storage ls -l "${g[@]}" "${BUCKET}/snapshots/018f/2026-11-04/"
    ;;
  detach)
    gcloud run jobs update "${JOB}" "${gr[@]}" \
      --remove-secrets="OPENAI_API_KEY,${DB_SECRET}" --clear-cloudsql-instances
    gcloud run jobs describe "${JOB}" "${gr[@]}" \
      --format='yaml(spec.template.metadata.annotations,spec.template.spec.template.spec.containers[0].env,spec.template.spec.template.spec.containers[0].image)'
    ;;
  teardown)
    docker rm -f proxy >/dev/null 2>&1 || true
    docker network rm "${NET}" >/dev/null 2>&1 || true
    gcloud sql instances delete "${INSTANCE}" "${g[@]}" --quiet
    gcloud secrets delete "${DB_SECRET}" "${g[@]}" --quiet
    rm -rf "${SECRET_DIR}"
    gcloud sql instances list "${g[@]}"
    gcloud sql backups list "${g[@]}" --instance=- 2>&1 | head -5 || true
    gcloud secrets list "${g[@]}" --format='value(name)'
    ;;
  *)
    sed -n '2,24p' "$0"; exit 1
    ;;
esac
