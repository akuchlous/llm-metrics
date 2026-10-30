# Project status

_Last updated: Step 004 — 2026-10-30_

## Current state

**Step 004 complete:** deterministic simulated TTFT history can be seeded for graphs.

Working:
- `./run.sh` creates/reuses `.venv`, runs tests, then measures TTFT.
- `APP_ENV=test` is the safe default; `prod` refuses to run.
- Successful measurements append to `data/llm_metrics.db`.
- `python3 -m llm_metrics.seed_history` adds 168 hourly simulated TTFT rows (2026-10-23 00:00 to 2026-10-29 23:00 UTC); re-running adds nothing.
- 38 standard-library `unittest` tests.
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

Seed simulated history (optional, `APP_ENV=test` only): `python3 -m llm_metrics.seed_history`.

## Architecture

```text
run.sh             venv -> tests -> measurement
llm_metrics/
  providers.py     DummyProvider + provider interface
  ttft.py          TTFT measurement
  storage.py       SQLite initialization + inserts
  seed_history.py  deterministic simulated TTFT history + seed command
  config.py        environment + DB path
  __main__.py      CLI
tests/             automated tests
prompts/           prompt history and guidance
data/              runtime DB; git-ignored
```

Flow: `environment → provider → measure TTFT → print → persist`.

SQLite table `observations` stores:
`id`, `recorded_at` (UTC), `environment`, `provider`, `model`, `metric`, `value_ms`.
A unique index on (`recorded_at`, `environment`, `provider`, `model`, `metric`) lets seeding skip existing rows; it is added automatically to older databases.

`LLM_METRICS_DB_PATH` can override the default DB path; tests use temporary databases. SQL values are parameterized.

## Known limitations

- Simulated provider only; one TTFT observation per run.
- Simulated history uses a fixed past week; it does not move with the current date.
- Seeded and live dummy rows are both `test`/`dummy`; they are told apart only by timestamp (seeded rows are on the hour, before 2026-10-30).
- No dashboard yet; data is written but not displayed.
- `value_ms` supports millisecond metrics; other units will require a schema decision.
- No migration mechanism yet.
- A storage failure currently surfaces as a traceback after measurement output.
- `.venv` has no pip until a dependency is justified.

## Next step

**Step 005 — first local TTFT graph.** A minimal local page or command that reads `observations` and shows TTFT over time for `environment = 'test'`, clearly labelled as simulated. Binds to `127.0.0.1` if a server is used.

Do not yet add other metrics, percentiles, real providers, scheduler, Docker, or cloud deployment.
