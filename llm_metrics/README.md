# `llm_metrics` package

## Purpose

This directory contains the executable application code for `llm-metrics`.

Its responsibility is to measure LLM-provider behavior, persist raw observations, calculate derived statistics, and present those measurements through the local dashboard. Documentation, implementation prompts, interview/design exercises, tests, and runtime data belong outside this package.

## Current modules

- `outcomes.py` — attempt outcomes: `success` and the stable internal failure categories; the observed success-rate calculation.
- `providers.py` — provider interface (text chunks, then a final `Usage` with token counts; `ProviderFailure(category)` on failure) and the simulated `DummyProvider` (simulated tokenizer, output cap, deterministic simulated failures).
- `latency.py` — metric catalogue (`METRICS`: label and unit per metric) and single-pass measurement of a benchmark attempt: outcome, token facts from `Usage`, plus (on success) total latency, TTFT, and output chunk throughput.
- `pricing.py` — the only place prices are defined (USD per 1M tokens), with their source and verification date (`PRICE_PROVENANCE`), and the per-request cost formula.
- `openai_provider.py` — the first real provider: OpenAI Responses API over `urllib` (no SDK), translating the event stream into text chunks + `Usage` and mapping errors to failure categories.
- `benchmark.py` — one attempt end to end (price lookup, measurement, save) and its printed summary; shared by the CLI and `real_smoke`.
- `real_smoke.py` — the only code path that spends money: one explicit real request, key from `OPENAI_API_KEY`; `--debug` prints sanitized failure diagnostics (never stored).
- `storage.py` — SQLite schema and transactional in-place upgrades; `save_request` (attempt row + linked observations in one transaction); time-window observation reads, request reads, and outcome counts.
- `seed_history.py` — deterministic simulated history used only in the test environment.
- `percentiles.py` — pure nearest-rank percentile calculation.
- `dashboard.py` — local server-rendered aggregate view, recent-attempts view (simulated or real), and Benchmark API Spend (real only).
- `config.py` — environment, database-path, and dashboard-port configuration.
- `__main__.py` — command-line entry point for one simulated attempt (never calls a paid API).

## Design boundaries

Keep measurement, storage, statistics, and presentation separate unless the implementation demonstrates a concrete reason to combine them. Prefer small modules with explicit responsibilities over speculative frameworks or abstractions.

Raw observations are the source of truth. Derived views such as percentiles belong in calculation/presentation layers unless scale later justifies materialized aggregates.

Production safety matters even while the project uses simulated data: test data must remain clearly separated from production, SQL values must remain parameterized, and the local dashboard must remain bound to loopback unless a future step deliberately changes that contract.

The current implementation is intentionally small. Add new modules or abstractions when a real requirement earns them, not in anticipation of hypothetical future features.
