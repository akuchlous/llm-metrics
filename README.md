# llm-metrics

An open-source project to independently measure LLM provider performance
(time to first token, throughput, latency, reliability, price).

It is being built in small, tested steps. **This is Step 001.**

> **Simulated data only.** The current implementation uses a dummy provider that
> sleeps for a fixed time and then emits fake tokens. Its numbers do **not**
> represent real LLM performance. No real LLM provider is called.

## What Step 001 measures

One metric: **Time To First Token (TTFT)**.

TTFT is the wall-clock time from the moment a request is started until the first
token of the streamed response is received. It is measured with
`time.perf_counter()` (monotonic, high resolution) and reported in milliseconds.

## Setup

Requires Python 3.10+. There are no third-party dependencies.

```bash
python3 -m venv .venv
source .venv/bin/activate
```

## Run the tests

From the repository root:

```bash
python -m unittest -v
```

## Run the dummy measurement

```bash
APP_ENV=test python -m llm_metrics
```

Example output:

```
Provider: dummy
Model: dummy-model-v1
Metric: TTFT
TTFT: 100.3 ms
```

## Environments

`APP_ENV` selects the environment:

| `APP_ENV`       | Behavior                                                  |
|-----------------|-----------------------------------------------------------|
| `test` (default)| Uses the dummy provider. Never calls a real LLM.          |
| `prod`          | Not supported yet. Exits with an error and measures nothing. |
| anything else   | Exits with an error.                                      |

Never commit secrets. `.env` is git-ignored.
