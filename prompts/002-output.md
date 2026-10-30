# Step 002 — Implementation report

Commit: `dd6d19b`. Prompt: `002-local-run-script.md`.

## What was implemented

`./run.sh`: creates or reuses `.venv`, runs all tests quietly, stops if any fail, then runs the TTFT CLI with `APP_ENV` defaulting to `test`.

## Files

- `run.sh` (new, executable in Git).
- `tests/test_run_script.py` (new).
- `README.md`, `PROJECT_STATUS.md`, `DECISIONS.md` (D011–D015).

## Tests / run

- 19 tests, OK (~1.5 s).
- `./run.sh` verified in the dev container: first run creates `.venv`, the second reuses it, and `APP_ENV=prod ./run.sh` exits 2.
- The project owner confirmed a successful `./run.sh` on a real Chromebook after this step.

## Design decisions and why

- **`venv --without-pip`.** Chromebook Linux is Debian, where plain `python3 -m venv` fails without the `python3-venv` package. The project has no dependencies, so pip isn't needed.
- **Call `.venv/bin/python` directly** instead of `source activate`. Same effect, with no dependence on shell state.
- **Respect an exported `APP_ENV`.** Forcing `test` would hide a wrong setting; respecting it lets `prod` reach the existing guard.
- **Test output is captured and shown only on failure**, which keeps a successful run short.

## Alternatives / tradeoffs

- **End-to-end test in a temporary copy.** It doesn't touch the real `.venv` and uses no shell-testing framework. Because `run.sh` runs the whole suite (including this test), the test sets `LLM_METRICS_INSIDE_RUN_SH_TEST=1` and the nested copy skips itself. This avoids recursion but leaves a test-only environment variable in the code.
- The end-to-end test creates a real venv, which costs about 1–2 s per suite run.

## Limitations / review questions

- Tested only on Linux with bash; not tested on macOS or Windows.
- The no-pip venv must change when the first dependency is added.
