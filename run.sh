#!/usr/bin/env bash
# One-command disposable local workflow using Docker Compose.
# Requires: docker with Compose v2 (docker compose, not docker-compose).
#
# Usage:
#   ./run.sh           Full workflow: offline+integration tests, seed, measure,
#                      dashboard on http://127.0.0.1:8000  (Ctrl+C to stop)
#   ./run.sh test      Same workflow; dashboard HTTP 200 smoke test; auto-exits
#   ./run.sh site-preview [--help]  Build the website and serve it locally
#                      on http://localhost:8000 (no deploy, no cloud calls)
#   ./run.sh down      Remove project containers, network and volume after
#                      a SIGKILL (safe, project-scoped — see cleanup below)
#
# Cleanup is project-scoped to Compose project name "llm_metrics".  It only
# removes containers, the internal network and the disposable db_data volume
# created by this project.  It never prunes or deletes unrelated host images,
# volumes or containers.
set -euo pipefail

cd "$(dirname "$0")"

# --- Prerequisites ---
if ! command -v docker &>/dev/null; then
    echo "✗ Docker is required but was not found." >&2
    echo "  Run ./setup.sh to check and install Docker." >&2
    echo "  On Google Cloud Shell: docker is pre-installed." >&2
    exit 1
fi
if ! docker compose version &>/dev/null 2>&1; then
    echo "✗ 'docker compose' (Compose v2) is required but was not found." >&2
    echo "  Run ./setup.sh to check and install the Compose plugin." >&2
    exit 1
fi

MODE="${1:-serve}"
if [ "$MODE" = "site-preview" ]; then
    # Local-only website preview; see scripts/site_preview.sh.
    shift
    exec bash scripts/site_preview.sh "$@"
fi
case "$MODE" in
    serve|test|down) ;;
    *)
        echo "Usage: ./run.sh [serve|test|down|site-preview]" >&2
        echo "  serve  Offline+integration tests, seed, measure, dashboard (default)" >&2
        echo "  test   Same as serve but runs dashboard smoke test and auto-exits" >&2
        echo "  down   Remove project Compose containers, network and volume" >&2
        echo "  site-preview  Build and serve the website locally (--help)" >&2
        exit 1
        ;;
esac

cleanup() {
    local ec=$?
    echo ""
    echo "Stopping and removing project Compose resources..."
    docker compose down -v --remove-orphans 2>/dev/null || true
    exit "$ec"
}

if [ "$MODE" = "down" ]; then
    echo "LLM Metrics — removing project Compose resources..."
    docker compose down -v --remove-orphans
    echo "✓ Done."
    exit 0
fi

trap cleanup EXIT

export COMPOSE_MODE="$MODE"

echo "LLM Metrics — Docker local environment (mode: $MODE)"
if [ "$MODE" = "serve" ]; then
    echo "Dashboard: http://127.0.0.1:8000  (Ctrl+C to stop)"
fi
echo ""

docker compose up --build --exit-code-from app --abort-on-container-exit
