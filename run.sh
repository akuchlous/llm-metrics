#!/usr/bin/env bash
# One-command local run: prepare .venv and its pinned dependencies, run the
# tests, seed simulated history (test mode only), run one simulated
# measurement, then serve the dashboard until Ctrl+C. Never calls a paid API.
# Usage: ./run.sh
set -euo pipefail

cd "$(dirname "$0")"

echo "LLM Metrics — local test environment"

if ! command -v python3 >/dev/null 2>&1; then
    echo "✗ python3 not found. Install Python 3.10 or newer." >&2
    exit 1
fi

# Created without pip, which avoids needing Debian's python3-venv package
# (missing on some Chromebooks); the installer below brings its own verified
# pip when one is needed.
if [ ! -x .venv/bin/python ]; then
    echo "  Creating Python environment in .venv ..."
    python3 -m venv --without-pip .venv
fi
PYTHON=.venv/bin/python
echo "✓ Python environment ready"

# Hash-checked install of requirements.txt. Needs the network only on the
# first run and after requirements.txt changes.
if ! "$PYTHON" -I scripts/install_requirements.py; then
    echo "✗ Dependencies are not installed. Not running the tests." >&2
    exit 1
fi

if ! test_output=$("$PYTHON" -m unittest 2>&1); then
    echo "$test_output" >&2
    echo "✗ Tests failed. Not starting the measurement." >&2
    exit 1
fi
echo "✓ Tests passed"

export APP_ENV="${APP_ENV:-test}"

# Idempotent: adds the fixed simulated week once, then nothing. Never in prod.
if [ "$APP_ENV" = "test" ]; then
    "$PYTHON" -m llm_metrics.seed_history
    echo "✓ Simulated history ready"
fi

echo "✓ Starting $APP_ENV measurement"
echo
"$PYTHON" -m llm_metrics
echo
exec "$PYTHON" -m llm_metrics.web
