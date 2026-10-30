# Design decisions

## Engineering principles

Treat every commit as public.

Priority: **correctness → security → readability/maintainability → simplicity → minimal code**.

> Write the smallest implementation that is easy to understand, test, modify, and operate safely.

Prefer clear code over fewer lines. Avoid duplication, speculative abstractions, unnecessary dependencies, configuration, and future-proofing. Add structure only when current requirements justify it.

Apply the same rules to documentation and prompts: concise, non-repetitive, scoped, and easy to maintain. Put shared rules here; prompts should reference them rather than repeat them.

Every step must preserve `./run.sh`, keep secrets/runtime artifacts out of Git, and pass independent review before the next step. Future local web servers bind to `127.0.0.1` by default.

## Decisions

- **D001 — Standard library first.** Add dependencies only when they provide clear value.
- **D002 — `unittest`.** Dependency-free tests for now.
- **D003 — No packaging yet.** Run with `python -m llm_metrics`.
- **D004 — Minimal provider interface.** `stream(prompt)`, `name`, `model`.
- **D005 — TTFT timer.** `time.perf_counter()` from request start to first yielded token.
- **D006 — Plain dict results.** `provider`, `model`, `metric`, `value_ms`; round only for display.
- **D007 — Safe environment default.** Unset `APP_ENV` means `test`; `prod` is the other valid value.
- **D008 — Production disabled until a real provider exists.** Never substitute dummy data.
- **D009 — No `.env` loading yet.** `.env` is ignored; no secrets exist.
- **D010 — CLI exit codes.** `0` success, `2` configuration error.
- **D011 — `./run.sh` is the local contract.** Keep it working after every step.
- **D012 — Venv without pip for now.** Revisit when a dependency is needed.
- **D013 — Use venv Python directly.** No shell activation required.
- **D014 — Respect explicit `APP_ENV`.** `run.sh` defaults to `test` only when unset.
- **D015 — Isolated run-script test.** End-to-end test runs in a temporary copy.
- **D016 — SQLite at `data/llm_metrics.db`.** Standard-library `sqlite3`; repo-root-relative; `data/` ignored.
- **D017 — One `observations` table.** `id`, `recorded_at`, `environment`, `provider`, `model`, `metric`, `value_ms`. `environment` separates simulated and future production data.
- **D018 — Initialize on connect; no migrations yet.** `CREATE TABLE IF NOT EXISTS` is idempotent.
- **D019 — UTC save timestamp.** `recorded_at` uses sortable ISO 8601 UTC text.
- **D020 — `LLM_METRICS_DB_PATH` override.** Used mainly to isolate tests.
- **D021 — Persist only successful measurements.** Dynamic SQL values use parameters.
