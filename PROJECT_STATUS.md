# Project status

_Last updated: Step 003 — 2026-10-30_

## Current state

**Step 003 complete:** TTFT measurements from the simulated provider are persisted to SQLite.

Working:
- `./run.sh` creates/reuses `.venv`, runs tests, then measures TTFT.
- `APP_ENV=test` is the safe default; `prod` refuses to run.
- Successful measurements append to `data/llm_metrics.db`.
- 28 standard-library `unittest` tests.
- No network calls, secrets, or third-party dependencies.

Current data is **simulated** and does not represent real LLM performance.

## Run

Requires Linux/Chromebook Linux and Python 3.10+.

```bash
git clone https://github.com/akuchlous/llm-metrics.git
cd llm-metrics
./run.sh
```

Tests only: `python -m unittest -v`.

## Architecture

```text
run.sh          venv -> tests -> measurement
llm_metrics/
  providers.py  DummyProvider + provider interface
  ttft.py       TTFT measurement
  storage.py    SQLite initialization + insert
  config.py     environment + DB path
  __main__.py   CLI
tests/          automated tests
prompts/        prompt history and guidance
data/           runtime DB; git-ignored
```

Flow: `environment → provider → measure TTFT → print → persist`.

SQLite table `observations` stores:
`id`, `recorded_at` (UTC), `environment`, `provider`, `model`, `metric`, `value_ms`.

`LLM_METRICS_DB_PATH` can override the default DB path; tests use temporary databases. SQL values are parameterized.

## Known limitations

- Simulated provider only; one TTFT observation per run.
- No historical dataset or dashboard yet.
- `value_ms` supports millisecond metrics; other units will require a schema decision.
- No migration mechanism yet.
- A storage failure currently surfaces as a traceback after measurement output.
- `.venv` has no pip until a dependency is justified.

## Next step

**Step 004 — deterministic historical simulated TTFT data.** Create enough reproducible test history for the first graph. Re-running must not duplicate seeded observations.

Do not yet add the dashboard, other metrics, real providers, scheduler, Docker, or cloud deployment.
