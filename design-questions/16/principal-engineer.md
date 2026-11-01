# Step 16 — Principal engineer

**Step context:** Step 016 added one real benchmark target per provider: OpenAI `gpt-6-luna`, Anthropic `claude-haiku-5-5`, Google `gemini-3.5-flash-lite` and xAI `grok-4.20-0309-non-reasoning`. Each target is defined by a versioned request profile in `llm_metrics/targets.py` (model, endpoint, output-cap field, every setting sent on purpose, reasoning condition, cache policy). The profile id is stored with every attempt (schema v7). Three new standard-library adapters share `http_streaming.py` with the OpenAI adapter, and costs now price provider-reported cached input at the cached rate. `python -m llm_metrics.real_benchmark --provider <name> --real` makes exactly one paid request to one chosen provider. No paid call was made in the step.

**Question:** Four providers expose different reasoning and caching controls. How do you compare them without inventing equivalences, and where does this design stop being right?

## Answer

Each profile records its provider's own control in that provider's terms:

- OpenAI: `reasoning.effort: none`.
- Anthropic: `thinking: disabled`.
- Gemini: `thinking_level: minimal`, which cannot be turned fully off.
- xAI: a non-reasoning model variant.

Cache policy uses the existing vocabulary truthfully. Only OpenAI sends a documented off switch (`disabled`); the other three run with the provider's default caching (`provider_default`), and any cached tokens they report are recorded and priced at the cached rate.

Comparisons are scoped to "these exact provider/model/profile combinations". The profile id makes the conditions visible in every row, so a later analysis can group by them and never silently pools different settings.

Usage is normalized only in protocol terms:
- **Input:** the whole prompt (Anthropic reports cache reads separately).
- **Cached:** the provider's cache-read count.
- **Output:** billed output including thinking.

Factual differences, such as different input counts for the same text, are kept.

The design stops being right when:
- **Many profiles per provider:** a constant registry and a string id per row become hard to query. Profiles would then need a table and analytics filters.
- **Per-request settings:** settings that vary per request (adaptive effort, routing) cannot be captured by one static profile.
- **Undocumented semantics:** a provider changes a meaning without changing the model id. The profile still says the same thing while the behavior differs, and only dated verification and live monitoring catch that.

## Critique

- **Good:** It makes the comparison's limits explicit in data, not just in prose.
- **Weak:** `reasoning` is free text, so it cannot be filtered on. The Gemini thought-token accounting rests on wording, not a live observation.
- **Improve:** After the pilot, record observed reasoning or thought tokens as their own fact, so "minimal thinking" becomes a measured quantity.
