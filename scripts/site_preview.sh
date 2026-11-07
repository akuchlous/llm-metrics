#!/usr/bin/env bash
# Local-only LLM Xchange website preview (invoked as ./run.sh site-preview).
#
# Usage:
#   ./run.sh site-preview [--analytics FILE] [--drafts] [--port N]
#   ./run.sh site-preview --help
#
# Builds the static site with the existing generator inside the project's
# Docker image, into the gitignored .site-preview/site, then serves it on
# http://localhost:PORT (default 8000) until Ctrl+C. Restart to rebuild.
#
# Default build = what a Cloudflare staging deploy would get: approved
# questions only, no dated editions, nothing frozen or archived, every page
# noindex, nofollow. Canonical URLs use the staging hostname; internal links
# are relative, so navigation stays on localhost.
#
#   --analytics FILE  A locally validated llm-metrics.analytics.v1 summary of
#                     real data (default: .site-preview/analytics.json when
#                     present). Shown through the provisional gates and label;
#                     without one the pages show the honest no-data state.
#   --drafts          Also show draft questions (review only; never deploy
#                     this build). Cannot be combined with --analytics.
#   --port N          Local port (default 8000).
#
# Never contacts OpenAI, Cloudflare or GCP, and never writes the archive.
set -euo pipefail
cd "$(dirname "$0")/.."

SITE_URL="https://llmxchange.akuchlous.workers.dev"
OUT=".site-preview"
PORT=8000
ANALYTICS=""
DRAFTS=0

usage() { sed -n '2,24p' "$0" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
    case "$1" in
        -h|--help) usage; exit 0 ;;
        --analytics) ANALYTICS="${2:?--analytics needs a file}"; shift 2 ;;
        --drafts) DRAFTS=1; shift ;;
        --port) PORT="${2:?--port needs a number}"; shift 2 ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
done
case "$PORT" in ''|*[!0-9]*) echo "--port must be a number" >&2; exit 2 ;; esac
if [ -z "$ANALYTICS" ] && [ -f "$OUT/analytics.json" ] && [ "$DRAFTS" = 0 ]; then
    ANALYTICS="$OUT/analytics.json"
fi
if [ -n "$ANALYTICS" ] && [ "$DRAFTS" = 1 ]; then
    echo "--drafts cannot be combined with --analytics." >&2; exit 2
fi

mkdir -p "$OUT"
IMAGE="llm_metrics-app"
echo "Building the project image (cached after the first run)..."
docker compose build app --quiet

NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
args=(--output /preview/site --site-url "$SITE_URL" --preview-at "$NOW")
mounts=(-v "$PWD:/src:ro" -v "$PWD/$OUT:/preview")
if [ "$DRAFTS" = 0 ]; then
    args+=(--staging)
fi
if [ -n "$ANALYTICS" ]; then
    [ -f "$ANALYTICS" ] || { echo "No such analytics file: $ANALYTICS" >&2; exit 2; }
    dir="$(cd "$(dirname "$ANALYTICS")" && pwd)"
    mounts+=(-v "$dir:/analytics:ro")
    args+=(--analytics "/analytics/$(basename "$ANALYTICS")" --data-source real --provisional-metrics)
    echo "Using analytics summary: $ANALYTICS"
else
    echo "No analytics summary: metric pages show the no-data state."
fi

echo "Building the site into $OUT/site ..."
docker run --rm --network none -u "$(id -u):$(id -g)" "${mounts[@]}" -w /src \
    -e PYTHONDONTWRITEBYTECODE=1 "$IMAGE" python -m llm_metrics.static_site "${args[@]}" \
    | grep -E '^(Built|Error)' || true
[ -f "$OUT/site/index.html" ] || { echo "✗ Build failed (see the error above)." >&2; exit 1; }
if [ -d llm_metrics/site_content/archive ] && [ -n "$(git status --porcelain -- llm_metrics/site_content/archive)" ]; then
    echo "✗ The publication archive changed; a preview must never write it." >&2; exit 1
fi

tty=()
[ -t 0 ] && tty=(-it)
echo ""
echo "  Open: http://localhost:$PORT"
echo ""
exec docker run --rm --init "${tty[@]}" -u "$(id -u):$(id -g)" \
    -p "127.0.0.1:$PORT:8000" -v "$PWD/$OUT/site:/site:ro" -w /src -v "$PWD:/src:ro" \
    -e PYTHONDONTWRITEBYTECODE=1 "$IMAGE" \
    python -m llm_metrics.site_preview --dir /site --host 0.0.0.0 --port 8000 \
    --url "http://localhost:$PORT"
