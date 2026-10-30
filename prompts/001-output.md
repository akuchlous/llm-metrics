# Step 001 — Implementation report

Commit: `c7363fa`. Prompt: `001-initial-ttft.md` (given in chat, archived afterwards in `a07e203`).

## What was implemented

A dependency-free Python package that measures TTFT against a simulated streaming provider, an `APP_ENV` switch (`test`/`prod`), and a CLI (`python -m llm_metrics`).

## Files

- `llm_metrics/providers.py` — `LLMProvider` (`stream`, `name`, `model`) and `DummyProvider` (sleep, then yield fixed tokens).
- `llm_metrics/ttft.py` — `measure_ttft()`; returns `provider`, `model`, `metric`, `value_ms`.
- `llm_metrics/config.py` — `get_app_env()`, `get_provider()`, `ConfigError`.
- `llm_metrics/__main__.py` — CLI.
- `tests/` — providers, TTFT, config, CLI (CLI tests run a subprocess).
- `README.md`, `PROJECT_STATUS.md`, `DECISIONS.md`, `.gitignore`.

## Tests / run

- `python -m unittest -v`: 16 tests, OK (~0.2 s).
- `APP_ENV=test python -m llm_metrics` printed `TTFT: 100.3 ms` (dummy delay 100 ms).
- `APP_ENV=prod` exited 2 with a clear error.

## Design decisions and why

- **Timer starts before `stream()` is called.** The dummy's delay runs inside the generator, so it is only counted if timing covers the first `next()`. A real provider's request latency will be included the same way.
- **Stop at the first token** (`break`) instead of draining the stream. Only TTFT was required.
- **`prod` raises instead of falling back to the dummy.** Simulated numbers must never look like production results.
- **`APP_ENV` unset defaults to `test`** (the safe side); values are case-sensitive.
- **Error on an empty stream** (`RuntimeError`) instead of returning a zero or `None` TTFT.

## Alternatives / tradeoffs

- pytest and `pyproject.toml` were left out to stay dependency-free. `unittest` is more verbose.
- Result is a plain dict, not a dataclass. Simpler, but has no type enforcement.
- No `.env.example`: nothing reads `.env` and there were no secrets, so it would have been empty.
- The delay test allows +200 ms of slack to avoid flaky failures on slow machines. It therefore checks the lower bound tightly and the upper bound loosely.

## Limitations / review questions

- Defaulting a missing `APP_ENV` to `test`, instead of failing, was flagged for review.
- One measurement per run with a fixed prompt; the numbers are simulated.
