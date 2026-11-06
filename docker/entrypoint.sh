#!/usr/bin/env bash
# In-container entrypoint for the llm-metrics Docker Compose local workflow.
#
# Runs all tests (offline + PostgreSQL integration), seeds simulated history,
# runs one simulated measurement, then either:
#   COMPOSE_MODE=serve (default) — starts the dashboard; Ctrl+C to stop
#   COMPOSE_MODE=test            — smoke-tests the dashboard (HTTP 200), exits
#
# LLM_METRICS_COMPOSE_RUN=1 is set by compose.yaml; integration tests use it
# to trust the Compose service hostname and skip DROP DATABASE (volume handles it).
set -euo pipefail

COMPOSE_MODE="${COMPOSE_MODE:-serve}"

echo "=== LLM Metrics — Docker local environment (mode: $COMPOSE_MODE) ==="
echo ""

echo "--- Running tests (offline + PostgreSQL integration) ---"
python -m unittest discover -s tests -v
echo ""

echo "--- Seeding simulated history ---"
python -m llm_metrics.seed_history
echo ""

echo "--- Running simulated measurement ---"
python -m llm_metrics
echo ""

if [ "$COMPOSE_MODE" = "test" ]; then
    echo "--- Starting dashboard for HTTP smoke test ---"
    # Smoke test runs from inside the container; loopback binding is sufficient.
    LLM_METRICS_HOST=127.0.0.1 python -m llm_metrics.web &
    DASHBOARD_PID=$!

    HTTP_STATUS=0
    for i in $(seq 1 20); do
        HTTP_STATUS=$(python -c "
import urllib.request
try:
    r = urllib.request.urlopen('http://127.0.0.1:8000/')
    print(r.getcode())
except Exception:
    print(0)
" 2>/dev/null)
        if [ "$HTTP_STATUS" = "200" ]; then
            break
        fi
        sleep 1
    done

    kill "$DASHBOARD_PID" 2>/dev/null || true
    wait "$DASHBOARD_PID" 2>/dev/null || true

    if [ "$HTTP_STATUS" = "200" ]; then
        echo "✓ Dashboard smoke test: HTTP 200"
        echo "✓ All done."
        exit 0
    else
        echo "✗ Dashboard smoke test failed (HTTP ${HTTP_STATUS:-timeout})" >&2
        exit 1
    fi
else
    echo "--- Starting dashboard (Ctrl+C stops and cleans up) ---"
    exec python -m llm_metrics.web
fi
