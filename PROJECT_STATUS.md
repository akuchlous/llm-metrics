# Project status

_Last updated: Step 002 — 2026-10-30_

## Objective

Independently measure LLM provider performance: TTFT, throughput, latency, reliability, and price. Build in small, tested steps.

## Current milestone

**Step 002 complete:** one-command local run.

Working now:
- Dummy streaming provider; no network calls.
- TTFT via `time.perf_counter()`.
- `APP_ENV=test` by default; `prod` safely refuses to run.
- `python -m llm_metrics` CLI.
- `./run.sh` creates/reuses `.venv`, runs tests, then measures TTFT.
- 19 standard-library `unittest` tests.

## Run

Requires Linux/Chromebook Linux and Python 3.10+.

```bash
git clone https://github.com/akuchlous/llm-metrics.git
cd llm-metrics
./run.sh
```

Tests only: `python -m unittest -v`.

Current output is simulated and does **not** represent real LLM performance.

## Architecture

```text
run.sh                 local entry point: venv -> tests -> measurement
llm_metrics/
  providers.py         LLMProvider + DummyProvider
  ttft.py              TTFT measurement
  config.py            test/prod configuration
  __main__.py          CLI
tests/                 automated tests
prompts/               development prompt history
```

Flow: `APP_ENV → provider → measure_ttft → CLI`.

TTFT result: `provider`, `model`, `metric`, `value_ms`.

## Constraints / limitations

- Simulated provider only; one TTFT measurement per run.
- No persistence, dashboard, real provider, or production execution yet.
- Standard library only; `.venv` currently has no pip.
- `.env` and `.venv` are ignored; no secrets are used.
- `./run.sh` must remain working after every step.

See `DECISIONS.md` for engineering principles and durable decisions.

## Next step

**Step 003 — SQLite persistence.** Save each successful TTFT observation with UTC timestamp, environment, provider, model, metric, and value using standard-library `sqlite3`. Runtime DB is git-ignored; tests use temporary DBs.

Do not yet add historical data, dashboard/web server, other metrics, real providers, scheduler, Docker, or cloud deployment.
