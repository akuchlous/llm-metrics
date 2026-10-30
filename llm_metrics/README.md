# `llm_metrics` package

## Purpose

This directory contains the executable application code for `llm-metrics`.

Its responsibility is to measure LLM-provider behavior, persist raw observations, calculate derived statistics, and present those measurements through the local dashboard. Documentation, implementation prompts, interview/design exercises, tests, and runtime data belong outside this package.

## Current modules

- `outcomes.py` — attempt outcomes: `success` and the stable internal failure categories; the observed success-rate calculation.
- `providers.py` — cache-policy vocabulary (`CACHE_POLICIES`); provider interface (text chunks, then a final `Usage` with token counts and optional cached input tokens; each provider's `cache_policy`; `ProviderFailure(category)` on failure) and the simulated `DummyProvider` (simulated tokenizer, output cap, deterministic simulated failures).
- `latency.py` — metric catalogue (`METRICS`: label and unit per metric) and single-pass measurement of a benchmark attempt: outcome, token facts from `Usage`, plus (on success) total latency, TTFT, and output token and chunk throughput.
- `pricing.py` — the only place prices are defined (USD per 1M tokens), with their source and verification date (`PRICE_PROVENANCE`), and the per-request cost formula.
- `openai_provider.py` — the first real provider: OpenAI Responses API over `urllib` (no SDK), translating the event stream into text chunks + `Usage` and mapping errors to failure categories.
- `benchmark.py` — one attempt end to end (price lookup, measurement, save) and its printed summary; shared by the CLI and `real_smoke`.
- `real_smoke.py` — the only code path that spends money: one explicit real request, key from `OPENAI_API_KEY`; `--debug` prints sanitized failure diagnostics (never stored).
- `storage.py` — SQLite schema and transactional in-place upgrades; `save_request` (attempt row + linked observations in one transaction); time-window observation reads, request reads, and outcome counts.
- `seed_history.py` — deterministic simulated history used only in the test environment.
- `percentiles.py` — pure nearest-rank percentile calculation.
- `analytics.py` — product analytics over stored data as natural values (no display formatting): metric windows with nearest-rank summaries and success rates, recent attempts, and real-only benchmark spend. Owns the population rules; reads only through `storage`.
- `query.py` — product query definitions shared by the dashboard and the JSON API: selectable metrics (and their units), window names and durations, data populations, the fixed aggregate population, single-valued parameter validation, and `load_aggregate_metric`.
- `dashboard.py` — dashboard page-specific query semantics and view preparation, without HTTP, HTML, or storage access: turns `analytics` results into view data (`*_view` / `load_*_view`) for the aggregate, recent requests, Benchmark API Spend, and invalid-query pages.
- `api.py` — JSON API v1 representation, without Flask: turns `analytics` results into JSON-ready facts (numbers, `None` for unknown, ISO 8601 UTC times) and error bodies. Never uses dashboard formatting.
- `web.py` — the Flask HTTP boundary: `create_app()` application factory, routes (HTML pages and `/api/v1/metrics`), template rendering (`render_page`), JSON encoding (`json_response`), status codes, security headers, and serving on 127.0.0.1. The only module that imports Flask or Jinja.
- `templates/` — Jinja templates (autoescaped, no logic beyond loops and prepared conditions); `static/dashboard.css` — the only stylesheet.
- `config.py` — environment, database-path, dashboard-port, and measurement-origin (`LLM_METRICS_ORIGIN_CLOUD` / `LLM_METRICS_ORIGIN_REGION`) configuration.
- `__main__.py` — command-line entry point for one simulated attempt (never calls a paid API).

## Design boundaries

Keep measurement, storage, statistics, and presentation separate unless the implementation demonstrates a concrete reason to combine them. Prefer small modules with explicit responsibilities over speculative frameworks or abstractions.

Raw observations are the source of truth. Derived views such as percentiles belong in calculation/presentation layers unless scale later justifies materialized aggregates.

Production safety matters even while the project uses simulated data: test data must remain clearly separated from production, SQL values must remain parameterized, and the local dashboard must remain bound to loopback unless a future step deliberately changes that contract.

The current implementation is intentionally small. Add new modules or abstractions when a real requirement earns them, not in anticipation of hypothetical future features.
