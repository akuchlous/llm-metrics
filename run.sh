#!/usr/bin/env bash
# One-command local run: prepare .venv, run the tests, then run the measurement.
# Usage: ./run.sh
set -euo pipefail

cd "$(dirname "$0")"

echo "LLM Metrics — local test environment"

if ! command -v python3 >/dev/null 2>&1; then
    echo "✗ python3 not found. Install Python 3.10 or newer." >&2
    exit 1
fi

# The project has no third-party dependencies, so pip is not needed. Skipping it
# also avoids needing Debian's python3-venv package (missing on some Chromebooks).
if [ ! -x .venv/bin/python ]; then
    echo "  Creating Python environment in .venv ..."
    python3 -m venv --without-pip .venv
fi
PYTHON=.venv/bin/python
echo "✓ Python environment ready"

if ! test_output=$("$PYTHON" -m unittest 2>&1); then
    echo "$test_output" >&2
    echo "✗ Tests failed. Not starting the measurement." >&2
    exit 1
fi
echo "✓ Tests passed"

export APP_ENV="${APP_ENV:-test}"
echo "✓ Starting $APP_ENV measurement"
echo
exec "$PYTHON" -m llm_metrics
