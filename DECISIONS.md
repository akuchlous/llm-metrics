# Design decisions

Each entry: the decision and why. Newest at the bottom.

## D001 — Standard library only
No third-party packages (including for tests). Step 001 needs only timing,
sleeping and a CLI, which the standard library covers. Fewer dependencies means
easier setup and review.

## D002 — `unittest` instead of pytest
Keeps the project dependency-free. Tests run with `python -m unittest`.
Can be revisited if pytest features become clearly useful.

## D003 — No `pyproject.toml` / packaging yet
The package runs directly from the repository root with `python -m llm_metrics`.
Packaging metadata adds nothing for Step 001.

## D004 — Provider abstraction is one method: `stream(prompt) -> Iterator[str]`
Plus `name` and `model` attributes. Streaming is required to observe the first
token. Anything more (async, options, token metadata) is deferred until a real
provider needs it.

## D005 — TTFT timer
`time.perf_counter()`: monotonic and highest available resolution. The timer
starts immediately before `provider.stream(prompt)` is called and stops when the
first token is yielded. For the dummy provider, the simulated delay runs inside
the generator, so it is included in the measurement.

## D006 — Result is a plain `dict`
Keys: `provider`, `model`, `metric` (`"ttft"`), `value_ms` (float, unrounded).
Simple to print, test and later serialize. Rounding happens only in CLI output.

## D007 — `APP_ENV` defaults to `test`
If `APP_ENV` is unset, the safe environment (`test`, dummy provider only) is used.
Any value other than `test` or `prod` (case-sensitive) is an error.

## D008 — `prod` fails until a real provider exists
`APP_ENV=prod` raises `ConfigError` and the CLI exits with code 2 without
measuring anything. This prevents simulated numbers from being reported as
production results.

## D009 — No `.env` loading and no `.env.example` yet
Nothing reads a `.env` file and there are no secrets yet, so `.env.example`
would have nothing useful in it. `.env` is git-ignored now so secrets cannot be
committed later by accident.

## D010 — CLI exit codes
`0` on success, `2` on configuration errors (message on stderr).

## D011 — `./run.sh` must always work
From Step 002 onward the repository must never be left in a state where
`./run.sh` does not work, and every step must preserve all previously working
functionality. `./run.sh` is the primary way to run the project locally, so it is
the baseline every change is checked against.

## D012 — `run.sh` creates `.venv` with `--without-pip`
The project has no third-party dependencies, so pip is not needed. On Debian
(including Chromebook Linux) plain `python3 -m venv` fails unless the
`python3-venv` package is installed; `--without-pip` avoids that. Revisit when
the first dependency is added.

## D013 — `run.sh` calls `.venv/bin/python` directly instead of `source activate`
Same effect for this script, fewer moving parts, and no dependence on the
caller's shell state. The venv is reused if `.venv/bin/python` exists.

## D014 — `run.sh` respects an already-set `APP_ENV`, defaulting to `test`
`APP_ENV=prod ./run.sh` therefore reaches the existing production guard and
exits with an error instead of silently running the dummy provider as `test`.

## D015 — End-to-end test of `run.sh` runs in a temporary copy
`tests/test_run_script.py` copies the code to a temp dir and runs `./run.sh` there
so the real `.venv` is untouched. Because `run.sh` runs the whole test suite, the
test sets `LLM_METRICS_INSIDE_RUN_SH_TEST=1` and the nested run skips it, to avoid
recursion.

## D016 — Engineering quality order
For implementation and review, prioritize: **correctness → security →
readability/maintainability → simplicity → minimal code**. Minimal line count is
not a goal by itself. A slightly longer implementation is preferred when it is
materially easier to understand, test, modify, or operate safely.

## D017 — Avoid premature complexity and code bloat
Implement only what the current step requires. Do not add abstractions,
dependencies, configuration, helpers, interfaces, or future-proofing merely
because they may be useful later. Good abstractions are welcome when current
code already justifies them. Prefer the smallest clear design, not the fewest
lines or the most generic architecture.

## D018 — Design as a public repository
Treat every committed file as potentially public. Never commit credentials,
API keys, secrets, `.env` files, runtime databases, virtual environments,
caches, or sensitive/private material. Each implementation step should include
a public-repository/security review before moving to the next step. When a local
web server is introduced, it must bind to loopback (`127.0.0.1`) by default and
must not expose itself on `0.0.0.0` unless explicitly requested and documented.

## D019 — Review gate between implementation steps
After Claude implements a numbered step, ChatGPT independently reviews the
actual repository changes for correctness, security/public-repository safety,
measurement methodology, readability/maintainability, simplicity, and code
bloat before the next numbered implementation prompt is created. A corrective
prompt takes precedence over advancing to the next feature when material issues
are found.
