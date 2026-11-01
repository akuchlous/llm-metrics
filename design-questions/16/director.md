# Step 16 — Director

**Step context:** Step 016 added one real benchmark target per provider: OpenAI `gpt-6-luna`, Anthropic `claude-haiku-5-5`, Google `gemini-3.5-flash-lite` and xAI `grok-4.20-0309-non-reasoning`. Each target is defined by a versioned request profile in `llm_metrics/targets.py` (model, endpoint, output-cap field, every setting sent on purpose, reasoning condition, cache policy). The profile id is stored with every attempt (schema v7). Three new standard-library adapters share `http_streaming.py` with the OpenAI adapter, and costs now price provider-reported cached input at the cached rate. `python -m llm_metrics.real_benchmark --provider <name> --real` makes exactly one paid request to one chosen provider. No paid call was made in the step.

**Question:** What does a four-provider capability let LLM Metrics claim, and what must it still not claim?

## Answer

It can claim that it:
- sends the same versioned workload to four major providers through one pipeline;
- records provider-reported tokens, cost basis, request ids, and the exact request settings of each measurement;
- separates failures caused by our setup from provider unreliability.

Once the pilot and the later experiment run, it can publish observed latency, reliability and cost **for these exact provider/model/request-profile combinations** under a documented methodology.

It must not claim:
- that the four models are equivalent in capability or quality;
- that "reasoning off" means the same thing everywhere (Gemini Flash-Lite cannot turn thinking fully off);
- that caching conditions match (only OpenAI's request disables caching);
- any universal "fastest provider" or winner;
- anything at all before real data exists. Today there is one OpenAI smoke sample and no cross-provider measurement.

## Critique

- **Good:** The comparability statement is in the code's documentation and every report, so marketing inherits the limits by default.
- **Weak:** The model choices are judgment calls ("smallest defensible option"), and a different choice per provider could change any headline.
- **Improve:** Publish the selection rationale with any results, and invite providers or users to propose alternative targets as new profiles.
