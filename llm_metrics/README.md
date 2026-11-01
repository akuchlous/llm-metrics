# `llm_metrics` package

## Purpose

This directory contains the executable application code for `llm-metrics`.

Its responsibility is to measure LLM-provider behavior, persist raw observations, calculate derived statistics, and present those measurements through the local dashboard. Documentation, implementation prompts, interview/design exercises, tests, and runtime data belong outside this package.

## Current modules

- `outcomes.py` — attempt outcomes: `success` and the stable internal failure categories; the observed success-rate calculation.
- `providers.py` — cache-policy vocabulary (`CACHE_POLICIES`); provider interface (text chunks, then a final `Usage` with token counts and optional cached input tokens; each provider's `cache_policy`; `ProviderFailure(category)` on failure) and the simulated `DummyProvider` (simulated tokenizer, output cap, deterministic simulated failures).
- `latency.py` — metric catalogue (`METRICS`: label and unit per metric) and single-pass measurement of a benchmark attempt: outcome, token facts from `Usage`, plus (on success) total latency, TTFT, and output token and chunk throughput.
- `pricing.py` — the only place prices are defined (USD per 1M tokens), with their source and verification date (`PRICE_PROVENANCE`), and the per-request cost formula.
- `targets.py` — benchmark targets and request profiles: frozen `RequestProfile` (versioned id, provider, exact model, endpoint, output-cap field, every deliberately sent request setting, reasoning/thinking condition, cache policy, API-key variable). `BENCHMARK_TARGETS` holds exactly one target per real provider (OpenAI, Anthropic, Google, xAI); `SIMULATED` is the dummy provider's profile. Adapters build their request bodies from their profile. Imports nothing from `llm_metrics`.
- `http_streaming.py` — HTTP streaming behavior shared by the real adapters: one request without retry, the shared HTTP status mapping (`status_failure`), usage validation (`checked_usage`), per-response failure identification and read-error mapping (`StreamContext`), SSE parsing, sanitizing diagnostics and ids, and the `RequestRejected` base class. LiteLLM was evaluated as a replacement and not adopted (D065).
- `openai_provider.py`, `anthropic_provider.py`, `google_provider.py`, `xai_provider.py` — the four real providers (OpenAI and xAI Responses APIs, Anthropic Messages API, Gemini Interactions API) over `urllib` (no SDKs): each translates its own event stream into text chunks + `Usage` and maps its own errors to failure categories or `RequestRejected`.
- `workloads.py` — the versioned benchmark workload catalogue: frozen `Workload` definitions (id, category, version, prompt, output cap, approximate size target) built deterministically from synthetic material; `get_workload` / `list_workloads`. Imports nothing from `llm_metrics`.
- `benchmark.py` — one catalogue workload run once end to end (profile and price checks, measurement, save with the request profile id and cost basis) and its printed summary; shared by the CLI, `real_smoke`, and `real_benchmark`.
- `real_benchmark.py` — the explicit paid pilot path: `--provider <name> --real [--workload <id>] [--debug]` makes exactly one real request to the one chosen benchmark target (key from that provider's variable only). Never loops over providers. `run(target, workload, debug)` is the one paid-attempt path.
- `real_smoke.py` — the low-cost OpenAI connectivity check: `real_benchmark.run` with the OpenAI target and the fixed smoke workload; `--debug` prints sanitized failure diagnostics (never stored). It and `real_benchmark` are the only code paths that spend money.
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
- `__main__.py` — command-line entry point for one simulated attempt of a chosen workload (`--workload`, default `interactive-chat-v1`; never calls a paid API).

## Design boundaries

Keep measurement, storage, statistics, and presentation separate unless the implementation demonstrates a concrete reason to combine them. Prefer small modules with explicit responsibilities over speculative frameworks or abstractions.

Raw observations are the source of truth. Derived views such as percentiles belong in calculation/presentation layers unless scale later justifies materialized aggregates.

Production safety matters even while the project uses simulated data: test data must remain clearly separated from production, SQL values must remain parameterized, and the local dashboard must remain bound to loopback unless a future step deliberately changes that contract.

The current implementation is intentionally small. Add new modules or abstractions when a real requirement earns them, not in anticipation of hypothetical future features.
