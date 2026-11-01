# Step 16 — Senior manager

**Step context:** Step 016 added one real benchmark target per provider: OpenAI `gpt-6-luna`, Anthropic `claude-haiku-5-5`, Google `gemini-3.5-flash-lite` and xAI `grok-4.20-0309-non-reasoning`. Each target is defined by a versioned request profile in `llm_metrics/targets.py` (model, endpoint, output-cap field, every setting sent on purpose, reasoning condition, cache policy). The profile id is stored with every attempt (schema v7). Three new standard-library adapters share `http_streaming.py` with the OpenAI adapter, and costs now price provider-reported cached input at the cached rate. `python -m llm_metrics.real_benchmark --provider <name> --real` makes exactly one paid request to one chosen provider. No paid call was made in the step.

**Question:** How did the team add three paid integrations without spending money or risking an accidental multi-provider run?

## Answer

- **Capability separated from execution.** Step 016 builds and tests the adapters against mocked fixtures shaped from official docs. The paid pilot is a separate step (016a) with its own review.
- **Explicit, narrow command.** `real_benchmark` needs both `--provider` and `--real`. It has no "all" option and no loop, and it reads only the chosen provider's key, so exporting four keys still gives exactly one request. Every refusal happens before network access, and tests block sockets to prove it.
- **Defaults stay safe.** `./run.sh`, the CLI and the test suite remain simulated and offline. Tests assert that the simulated paths never import the real adapters.
- **Reviewable evidence.** The report lists the model, endpoint, usage mapping, request-id source, cache and reasoning semantics, price and official source for each provider. A reviewer can check every claim before the pilot.
- **Bounded cost.** The pilot is four requests, about $0.006 in total at the verified rates.

## Critique

- **Good:** Spending requires a deliberate human action per provider, and a reviewer can audit the decision trail.
- **Weak:** Three adapters have never seen real traffic. Docs can be incomplete, and some facts (Gemini thought-token accounting, xAI error codes) are assumptions.
- **Improve:** Treat 016a as validation, not results. Run each provider with `--debug`, compare stored usage with each provider's console, and fix adapters before any repeated runs.
