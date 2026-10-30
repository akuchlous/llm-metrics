# Project status

_Last updated: Step 002 (2026-10-30)_

## Project objective

`llm-metrics` will independently measure LLM provider performance: TTFT,
throughput, latency, reliability and price. It is built in very small,
individually tested and committed steps. Only what each step asks for is built.

## Current milestone

**Step 002 complete: one-command local run (`./run.sh`).**
Step 001 (TTFT against a simulated provider) is unchanged.

## Working right now

- [x] Simulated streaming provider (`DummyProvider`), no network calls
- [x] TTFT measurement in milliseconds (`time.perf_counter`)
- [x] `APP_ENV=test` (default) uses the dummy provider
- [x] `APP_ENV=prod` refuses to run (no real provider yet); invalid `APP_ENV` fails clearly
- [x] CLI: `python -m llm_metrics`
- [x] `./run.sh`: creates/reuses `.venv`, runs all tests, stops if any fail, then runs the measurement
- [x] 19 automated tests, standard library only

## Current user experience

From a Chromebook Linux terminal (or any Linux with Python 3.10+):

```bash
git clone https://github.com/akuchlous/llm-metrics.git
cd llm-metrics
./run.sh
```

## What I can see

First run (later runs skip the "Creating" line):

```
LLM Metrics — local test environment
  Creating Python environment in .venv ...
✓ Python environment ready
✓ Tests passed
✓ Starting test measurement

Provider: dummy
Model: dummy-model-v1
Metric: TTFT
TTFT: 100.5 ms
```

If a test fails: the unittest output is printed, then
`✗ Tests failed. Not starting the measurement.`, exit code 1.

`APP_ENV=prod ./run.sh`: tests pass, then
`Error: APP_ENV=prod has no real provider yet. ...`, exit code 2.

## Current architecture

Pure Python standard library, no third-party dependencies.

```
run.sh           one-command local run (bash): .venv -> tests -> measurement
llm_metrics/
  providers.py   LLMProvider base class (stream(prompt) -> Iterator[str], name, model)
                 DummyProvider: sleeps first_token_delay_s (default 0.1), then yields fake tokens
  ttft.py        measure_ttft(provider, prompt) -> dict
  config.py      get_app_env(environ) -> "test" | "prod"; get_provider(app_env); ConfigError
  __main__.py    CLI: python -m llm_metrics
tests/           unittest tests, one file per module plus CLI and run.sh
prompts/         immutable history of step prompts (do not edit existing files)
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
- `.venv` is created by `./run.sh` with `python3 -m venv --without-pip` (works
  without Debian's `python3-venv` package). `.venv` is git-ignored.
- `APP_ENV=test` (default when unset): uses `DummyProvider`. Never calls a real LLM.
- `APP_ENV=prod`: raises `ConfigError`; the CLI prints an error and exits with code 2.
- Any other `APP_ENV` value (case-sensitive): `ConfigError`, exit code 2.
- `./run.sh` keeps an already-exported `APP_ENV`, otherwise uses `test`.
- No secrets exist. `.env` is git-ignored. Nothing loads `.env` files.

## What has been implemented

- Step 001: TTFT measurement against a simulated streaming provider, the
  `test`/`prod` environment switch, and a CLI.
- Step 002: `./run.sh` one-command local run, its tests, and docs.

## What tests exist

Run with `python -m unittest -v` (19 tests, about 2 seconds). `./run.sh` also runs them.

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
- `tests/test_run_script.py`: `run.sh` is executable and passes `bash -n`;
  end-to-end in a temporary copy: first run creates `.venv` and prints TTFT,
  second run reuses `.venv`, and an added failing test stops the run before the
  measurement. The end-to-end test skips itself when run from inside `run.sh`
  (`LLM_METRICS_INSIDE_RUN_SH_TEST=1`) to avoid recursion.

## How to run the project

```bash
./run.sh                             # normal way
python -m unittest -v                # tests only
APP_ENV=test python -m llm_metrics   # measurement only
```

## Current limitations

- Only simulated data. Numbers do not represent any real LLM.
- One metric (TTFT), one measurement per run, fixed prompt and fixed 100 ms dummy delay.
- No real providers, no persistence, no output formats besides plain text.
- `prod` cannot run anything yet.
- `run.sh` needs bash; tested on Linux only (not macOS or Windows).
- The `.venv` has no pip. A future step that adds a dependency must change that.

## Decisions made

See `DECISIONS.md` (D001 to D015). Summary: standard library only; `unittest`;
no packaging; one-method provider interface; `perf_counter` timer; result is a
dict; `APP_ENV` defaults to `test`; `prod` fails until a real provider exists;
no `.env` loading yet; exit code 2 on config errors; **`./run.sh` must always
work (D011)**; venv without pip; `run.sh` uses `.venv/bin/python` directly;
`run.sh` respects an exported `APP_ENV`; `run.sh` end-to-end test runs in a temp copy.

## Next recommended micro-step

**Step 003: save each TTFT observation to a local SQLite file.**
After measuring, the CLI appends the result (provider, model, metric, value_ms,
plus a UTC timestamp and APP_ENV) as one row to a SQLite database at a
git-ignored path, using Python's built-in `sqlite3`. Tests use a temporary
database file. `./run.sh` keeps working and its output stays the same apart from
one line saying where the observation was saved.

## Do NOT implement yet

- Historical or generated dummy data (planned Step 004)
- Dashboard, web server, Flask/FastAPI, JavaScript or charting libraries (planned Step 005)
- Total response time, throughput, p50/p95/p99
- Real LLM providers or credentials
- Scheduler, Docker, cloud deployment, GitHub Actions
