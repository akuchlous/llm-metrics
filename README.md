# llm-metrics

An open-source project to independently measure LLM provider performance
(time to first token, throughput, latency, reliability, price).

It is being built in small, tested steps. **Current step: 002.**

> **Simulated data only.** The current implementation uses a dummy provider that
> sleeps for a fixed time and then emits fake tokens. Its numbers do **not**
> represent real LLM performance. No real LLM provider is called.

## What it measures (so far)

One metric: **Time To First Token (TTFT)**.

TTFT is the wall-clock time from the moment a request is started until the first
token of the streamed response is received. It is measured with
`time.perf_counter()` (monotonic, high resolution) and reported in milliseconds.

## Quick start (Chromebook Linux terminal or any Linux)

Requires Python 3.10+. There are no third-party dependencies.

```bash
git clone https://github.com/akuchlous/llm-metrics.git
cd llm-metrics
./run.sh
```

`./run.sh` creates a `.venv` virtual environment on first run (and reuses it
afterwards), runs all tests, and only if they pass runs the TTFT measurement in
`test` mode:

```
LLM Metrics — local test environment
✓ Python environment ready
✓ Tests passed
✓ Starting test measurement

Provider: dummy
Model: dummy-model-v1
Metric: TTFT
TTFT: 100.3 ms
```

If any test fails, the test output is shown and the measurement is not run.

## Manual commands (for development and debugging)

From the repository root:

```bash
python3 -m venv --without-pip .venv   # no dependencies, so no pip needed
source .venv/bin/activate
python -m unittest -v               # run the tests
APP_ENV=test python -m llm_metrics  # run the dummy measurement
```

## Environments

`APP_ENV` selects the environment:

| `APP_ENV`       | Behavior                                                  |
|-----------------|-----------------------------------------------------------|
| `test` (default)| Uses the dummy provider. Never calls a real LLM.          |
| `prod`          | Not supported yet. Exits with an error and measures nothing. |
| anything else   | Exits with an error.                                      |

Never commit secrets. `.env` is git-ignored.
