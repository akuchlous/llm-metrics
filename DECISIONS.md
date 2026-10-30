# Design decisions

## Engineering principles

Treat every committed file as public.

Priority: **correctness → security → readability/maintainability → simplicity → minimal code**.

> Write the smallest implementation that is easy to understand, test, modify, and operate safely.

Minimal line count is not the goal. Avoid speculative abstractions, dependencies, configuration, and future-proofing; add them only when current requirements justify them.

Every step must preserve `./run.sh`, avoid secrets/runtime artifacts in Git, and be independently reviewed for correctness, security, measurement integrity, maintainability, simplicity, and bloat before the next step. Future local web servers bind to `127.0.0.1` by default.

## Decisions

- **D001 — Standard library first.** No third-party packages until they provide clear value.
- **D002 — `unittest`.** Keeps tests dependency-free for now.
- **D003 — No packaging yet.** Run directly with `python -m llm_metrics`.
- **D004 — Minimal provider interface.** `stream(prompt)`, plus `name` and `model`.
- **D005 — TTFT timer.** Use `time.perf_counter()` from request start to first yielded token.
- **D006 — Plain dict results.** `provider`, `model`, `metric`, `value_ms`; round only for display.
- **D007 — Safe default environment.** Unset `APP_ENV` means `test`; other valid value is `prod`.
- **D008 — Production disabled until real provider exists.** `prod` fails clearly; never substitutes dummy data.
- **D009 — No `.env` loading yet.** `.env` is ignored; there are currently no secrets.
- **D010 — CLI exit codes.** `0` success, `2` configuration error.
- **D011 — `./run.sh` is the local contract.** Every step must keep it working.
- **D012 — Venv without pip for now.** `run.sh` uses `python3 -m venv --without-pip`; revisit when a dependency is needed.
- **D013 — Use venv Python directly.** `run.sh` calls `.venv/bin/python` rather than activating the shell.
- **D014 — Respect explicit `APP_ENV`.** `run.sh` defaults to `test` but preserves an exported value.
- **D015 — Isolated run-script test.** End-to-end `run.sh` testing uses a temporary copy and avoids recursive self-testing.
