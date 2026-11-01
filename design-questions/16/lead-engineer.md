# Step 16 — Lead engineer

**Step context:** Step 016 added one real benchmark target per provider: OpenAI `gpt-6-luna`, Anthropic `claude-haiku-5-5`, Google `gemini-3.5-flash-lite` and xAI `grok-4.20-0309-non-reasoning`. Each target is defined by a versioned request profile in `llm_metrics/targets.py` (model, endpoint, output-cap field, every setting sent on purpose, reasoning condition, cache policy). The profile id is stored with every attempt (schema v7). Three new standard-library adapters share `http_streaming.py` with the OpenAI adapter, and costs now price provider-reported cached input at the cached rate. `python -m llm_metrics.real_benchmark --provider <name> --real` makes exactly one paid request to one chosen provider. No paid call was made in the step.

**Question:** How do you make sure the stored request profile always describes the request that was actually sent?

## Answer

The profile is used as input, not as documentation:

1. **Bodies are built from the profile.** Each adapter starts from the fixed fields (model, prompt, cap, `stream`) and calls `PROFILE.apply_settings(body)`. The settings are (dotted path, JSON text) pairs, so a value in the profile is exactly the value on the wire, including nested fields such as `generation_config.thinking_level`.
2. **The run refuses mismatches.** `benchmark.run_attempt` requires that `provider.request_profile` is the registered profile for its id. It also requires that the provider's `name`, `model` and `cache_policy` equal the profile's. An adapter whose model was changed, or a provider with no profile, fails before pricing, the call, or any write.
3. **Changes are caught by tests.** `tests/test_targets.py` pins every field of all four profiles, and the adapter tests assert each full request body. Editing a setting fails both, which pushes the change into a new `.v2` profile.

Fields that are not sent are described as provider defaults (for example Anthropic's effort), never given an assumed value.

## Critique

- **Good:** One source of truth that the code executes, so documentation and behavior cannot drift.
- **Weak:** Headers (`anthropic-version`) and the endpoint URL live in the adapter, and the profile only describes them in text. The endpoint path is checked by tests, not built from the profile.
- **Improve:** Build the URL and version header from the profile too, or pin them in the same golden test as the settings.
