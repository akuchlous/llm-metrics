"""llm-metrics: measure LLM provider latency, throughput, cost, and reliability.

The package is organized by responsibility, with dependencies flowing one way:
entry points (`__main__`, `real_smoke`, `seed_history`, `dashboard`) use
`benchmark`, which uses providers, measurement (`latency`), `pricing`, and
`storage`. Providers, measurement, pricing, and storage never import the entry
points or the dashboard.
"""
