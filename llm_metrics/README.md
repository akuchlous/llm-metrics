# `llm_metrics` package

## Purpose

This directory contains the executable application code for `llm-metrics`.

Its responsibility is to measure LLM-provider behavior, persist raw observations, calculate derived statistics, and present those measurements through the local dashboard. Documentation, implementation prompts, interview/design exercises, tests, and runtime data belong outside this package.

## Current modules

- `providers.py` — provider interface and the current simulated `DummyProvider`.
- `ttft.py` — streaming measurement logic for time to first token (TTFT).
- `storage.py` — SQLite schema, observation writes, and filtered observation reads.
- `seed_history.py` — deterministic simulated history used only in the test environment.
- `percentiles.py` — pure nearest-rank percentile calculation.
- `dashboard.py` — local server-rendered dashboard and time-window selection.
- `config.py` — environment, database-path, and dashboard-port configuration.
- `__main__.py` — command-line entry point for taking and storing a measurement.

## Design boundaries

Keep measurement, storage, statistics, and presentation separate unless the implementation demonstrates a concrete reason to combine them. Prefer small modules with explicit responsibilities over speculative frameworks or abstractions.

Raw observations are the source of truth. Derived views such as percentiles belong in calculation/presentation layers unless scale later justifies materialized aggregates.

Production safety matters even while the project uses simulated data: test data must remain clearly separated from production, SQL values must remain parameterized, and the local dashboard must remain bound to loopback unless a future step deliberately changes that contract.

The current implementation is intentionally small. Add new modules or abstractions when a real requirement earns them, not in anticipation of hypothetical future features.
