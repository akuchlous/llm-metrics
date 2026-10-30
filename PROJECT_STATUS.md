# Project status

_Last updated: Step 001 (2026-10-30)_

## Project objective

`llm-metrics` will independently measure LLM provider performance: TTFT,
throughput, latency, reliability and price. It is built in very small,
individually tested and committed steps. Only what each step asks for is built.

## Current architecture

Pure Python standard library, no third-party dependencies.

```
llm_metrics/
  providers.py   LLMProvider base class (stream(prompt) -> Iterator[str], name, model)
                 DummyProvider: sleeps first_token_delay_s (default 0.1), then yields fake tokens
  ttft.py        measure_ttft(provider, prompt) -> dict
  config.py      get_app_env(environ) -> "test" | "prod"; get_provider(app_env); ConfigError
  __main__.py    CLI: python -m llm_metrics
tests/           unittest tests, one file per module plus CLI
```

Flow: `APP_ENV` → `get_app_env` → `get_provider` → `DummyProvider` →
`measure_ttft` → result dict → CLI prints it.

TTFT result schema (plain dict):

| key        | type  | example            |
|------------|-------|--------------------|
| `provider` | str   | `"dummy"`          |
| `model`    | str   | `"dummy-model-v1"` |
| `metric`   | str   | `"ttft"`           |
| `value_ms` | float | `100.3` (unrounded)|

## Current environment setup

- Python 3.10+ (developed on 3.13). No packages to install.
- `APP_ENV=test` (default when unset): uses `DummyProvider`. Never calls a real LLM.
- `APP_ENV=prod`: raises `ConfigError`; the CLI prints an error and exits with code 2.
  No real provider exists yet.
- Any other `APP_ENV` value (case-sensitive): `ConfigError`, exit code 2.
- No secrets exist. `.env` is git-ignored. Nothing loads `.env` files.

## What has been implemented

- Step 001: TTFT measurement against a simulated streaming provider, the
  `test`/`prod` environment switch, and a CLI.

## What tests exist

Run with `python -m unittest -v` (16 tests, under 1 second).

- `tests/test_providers.py`: DummyProvider emits the configured tokens, default
  tokens are non-empty, it is an `LLMProvider` with the expected name and model.
- `tests/test_ttft.py`: result fields; value is positive; a 50 ms configured
  delay gives a TTFT of at least 50 ms and less than 250 ms; a provider that
  yields no tokens raises `RuntimeError`.
- `tests/test_config.py`: `test`/`prod` are read; default is `test`; invalid
  values (`production`, `TEST`, `""`, `dev`) fail with "Invalid APP_ENV";
  `test` gives DummyProvider; `prod` raises instead of returning DummyProvider;
  an invalid env passed to `get_provider` fails.
- `tests/test_cli.py` (runs the CLI as a subprocess): `test` prints provider,
  model, metric and TTFT; `prod` exits 2 with an error and no measurement
  output; an invalid env exits 2 with "Invalid APP_ENV".

## How to run the project

```bash
python3 -m venv .venv && source .venv/bin/activate   # optional, no deps
python -m unittest -v
APP_ENV=test python -m llm_metrics
```

## Current limitations

- Only simulated data. Numbers do not represent any real LLM.
- One metric (TTFT), one measurement per run, fixed prompt and fixed 100 ms dummy delay.
- No real providers, no persistence, no output formats besides plain text.
- `prod` cannot run anything yet.

## Decisions made

See `DECISIONS.md` (D001 to D010). Summary: standard library only; `unittest`;
no packaging yet; one-method provider interface; `perf_counter` timer; result is a
dict; `APP_ENV` defaults to `test`; `prod` fails until a real provider exists;
no `.env` loading yet; exit code 2 on config errors.

## Next recommended micro-step

**Step 002: measure total response time with the dummy provider.**
Add a function that measures the wall-clock time from request start until the
last token is received (the stream is exhausted), returning the same dict schema
with `metric: "total_time"`. Give `DummyProvider` an optional per-token delay
(default 0) so the test can check that total time is roughly
`first_token_delay + per_token_delay × (number of tokens - 1)`. Print it in the CLI
below TTFT. No real providers, no other metrics.
