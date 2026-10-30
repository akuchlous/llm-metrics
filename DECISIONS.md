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
- **D006 — Plain dict results.** `provider`, `model`, `metric`, `value` (unit fixed by `metric`, see D035); round only for display. _Revised in Step 009: key was `value_ms`._
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
- **D017 — One `observations` table.** `id`, `recorded_at`, `environment`, `provider`, `model`, `metric`, `value`. `environment` separates simulated and future production data. _Revised in Step 009: `value_ms` renamed to `value` because throughput is not in milliseconds; storing it under `value_ms` would have made the schema lie._
- **D018 — Initialize and upgrade on connect.** `CREATE TABLE IF NOT EXISTS` is idempotent; schema changes use `PRAGMA user_version` with ordered in-place upgrades in `storage._upgrade` (no framework). A database newer than the code is refused. _Revised in Step 009: previously no migrations; version 1 renamed `value_ms` → `value` and keeps all rows._
- **D019 — UTC save timestamp.** `recorded_at` uses sortable ISO 8601 UTC text.
- **D020 — `LLM_METRICS_DB_PATH` override.** Used mainly to isolate tests.
- **D021 — Persist only successful measurements.** Dynamic SQL values use parameters.
- **D022 — Fixed simulated history window.** Seeded TTFT history covers 2026-10-23 00:00 to 2026-10-29 23:00 UTC, hourly, from a fixed random seed. Fully reproducible; it does not move with the current date. Live measurements keep the save time (D019).
- **D023 — Idempotence via unique index.** `UNIQUE (recorded_at, environment, provider, model, metric)` plus `INSERT OR IGNORE` for seeding. Created with `CREATE UNIQUE INDEX IF NOT EXISTS`, so Step 003 databases gain it without a migration. Live inserts stay plain `INSERT`.
- **D024 — Seeding is test-only.** `python -m llm_metrics.seed_history` requires `APP_ENV=test` and writes only `environment = 'test'` rows. `./run.sh` runs it (idempotently) before the live measurement in `test` so a fresh clone has a meaningful graph, and never in `prod`.
- **D025 — Dashboard uses only the standard library.** `http.server` plus a server-rendered SVG chart; no web framework, no JavaScript, no charting library. The smallest justified dependency was none: adding one would require pip in `.venv` (D012) and a network install on first run.
- **D026 — Dashboard binds to `127.0.0.1` only.** The host is a constant, not configurable. Pages send a strict `Content-Security-Policy` (no scripts or external loads).
- **D027 — Dashboard shows simulated TTFT for a selected time window.** Filtered to `test` / dummy / `ttft`, ordered by `recorded_at`; the x-axis is proportional to real time and spans the window. _Revised in Step 007: originally showed all rows with no window so the fixed seeded week stayed visible; real time windows replaced that, and old seeded data may now fall outside them._
- **D028 — `LLM_METRICS_PORT`.** Default `8000`; `0` picks a free port. The real bound URL is printed after binding, which lets tests run `./run.sh` without port conflicts.
- **D029 — `./run.sh` ends by serving the dashboard.** Tests → seed (test only) → measurement → dashboard (`exec`, Ctrl+C stops). A failed test or measurement (including `prod`) stops before the dashboard starts.
- **D030 — Nearest-rank percentiles.** p50/p95/p99 use rank `ceil(p·n/100)` on sorted values, computed in integer arithmetic in `percentiles.py` (no HTML). Always an observed value, order-independent, deterministic for small n; preferred over interpolation because it never reports a latency that was not measured.
- **D031 — Time windows relative to current UTC.** `24h`, `7d`, `30d` via `/?window=`; bounds `now − window <= recorded_at <= now`, both inclusive (future-dated rows excluded). Filtering happens in SQL in `load_observations`. Default `7d` because hourly data then gives ~168 samples, enough for nearest-rank p99 to differ from the maximum. Any other value, empty value, or repeated `window` returns HTTP 400 listing valid choices; the value is not echoed.
- **D032 — `total_latency` metric, single pass.** Total response latency is stored with metric name `total_latency` (milliseconds): from the same request start as TTFT until the stream is fully consumed. `measure_request()` invokes the provider once and returns all results (renamed from `measure_latency()` in Step 009); TTFT semantics are unchanged. Both rows are saved in one transaction with the same `recorded_at`; if the stream fails, neither is saved. The dummy provider waits `inter_token_delay_s` (default 20 ms) between tokens so the two metrics differ.
- **D033 — Dashboard metric selector.** `/?metric=ttft|total_latency` (default `ttft`, the established headline metric) alongside `window`. Unknown, empty, or repeated values return HTTP 400, as for `window` (D031); input is never echoed. Each link keeps the other current selection.
- **D034 — `output_chunks_per_s` throughput.** Output throughput after the first chunk: `(non-empty chunks − 1) / (time of last non-empty chunk − time of first non-empty chunk)`, in chunks per second. A chunk is one non-empty item yielded by `provider.stream()` (for the dummy provider, one simulated token); it is not an API/tokenizer token count, and a real provider must keep that meaning or use a new metric name. Excluding the first chunk's wait keeps throughput independent of TTFT. Not recorded when undefined (fewer than 2 non-empty chunks, or zero elapsed time). Same single pass and transaction as D032.
- **D035 — Metric catalogue.** `llm_metrics.latency.METRICS` maps each metric name to its display label and unit (`ttft`, `total_latency`: ms; `output_chunks_per_s`: chunks/s). The name fixes the unit; never store a different unit under an existing name. The CLI and dashboard read labels and units from it.
