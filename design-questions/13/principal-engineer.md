# Step 13 — Principal engineer

**Step context:** Step 013 completed the Metrics v1 request data model. It added `output_tokens_per_s` (provider-reported output tokens over the first-to-last output chunk interval), a required `workload_id` naming the benchmark case, and `origin_cloud` / `origin_region` for where the runner executed (configured by environment variables, default `local` / `unknown`). It also added cache facts: the requested `cache_policy` (the OpenAI smoke request sends explicit cache mode with no breakpoints and records `disabled`; the simulated provider records `provider_default`) and provider-reported `cached_input_tokens` (0 = reported zero, NULL = not reported). Schema versions 5 and 6 add these as request columns; historical rows stay NULL, with cache policy `unknown`.

**Question:** Why are workload and origin request columns, how did the migration avoid fabricating history, and what keeps a `workload_id` meaningful?

## Answer

Dimensions describe the conditions of a request; metrics describe what happened. As `requests` columns, workload and origin also apply to failed attempts, which have no observations. They can filter the success rate and every metric population with the same `WHERE`, and they don't multiply metric rows.

The version 5 upgrade is three `ALTER TABLE ADD COLUMN` statements inside the existing `BEGIN IMMEDIATE` transaction: no rebuild, and existing values untouched. Historical rows stay NULL.

It was tempting to label old prod rows `smoke.short_text.v1`, because `real_smoke` was the only real path. But the first real attempt was sent without `reasoning.effort` and later ones with `none`: two different cases. Guessing would merge them.

New rows can't be NULL: `run_attempt` takes `workload_id` and `origin` as keyword-only arguments with no defaults, and `save_request` raises on a missing or empty value. A `workload_id` stays meaningful by convention: `<family>.<case>.v<N>`, with the version bumped whenever the prompt, cap or request shape changes. The constants carry a comment saying so.

## Critique

- **Good:** It's a cheap, transactional migration with honest unknowns. Enforcing the facts in code keeps the columns nullable without placeholder defaults. Filtering needs no redesign.
- **Weak:** The version-bump rule is a convention; nothing detects a prompt change under the same id. Workload identity doesn't describe input size or category yet, so populations are only as coherent as the id's discipline.
- **Improve:** Derive a short fingerprint of the request shape (prompt hash, cap, parameters) and store it beside the id. Or add a test that pins each workload constant's prompt and cap, so an edit fails until the version is bumped.

**Question 2:** Why store the requested cache policy and the reported cached input tokens as two separate facts, and how do you stop cached and uncached samples from being averaged together?

## Answer

They come from different sources and can disagree.

- **`cache_policy`** is ours: what the request asked for. Each provider declares it (`LLMProvider.cache_policy`), and it's sent with every request, so the stored value can't drift from the body. OpenAI's is `disabled` because it sends `prompt_cache_options: {"mode": "explicit"}` with no breakpoints, which the official guide says "does not use prompt caching or create cache writes".
- **`cached_input_tokens`** is the provider's: `usage.input_tokens_details.cached_tokens`. A reported `0` is stored as 0; an absent field is NULL. Nothing is inferred from latency or repeated prompts.

So "uncached / cold-ish" is a claim backed by a documented control and/or a reported zero, never by a missing value.

Populations: the vocabulary is constrained by a column CHECK (`disabled`, `enabled`, `provider_default`, `unknown`), and history is honestly `unknown`. `load_observations(..., cache_policy=...)` restricts any metric to one policy through the observation's request, with no schema change. Mixed views remain possible but are now a deliberate choice.

## Critique

- **Good:** It separates intent from evidence, keeps 0 distinct from unknown, and grounds `disabled` in a cited control. The migration doesn't guess.
- **Weak:** gpt-6-luna isn't named in the guide, and the control hasn't been exercised live. The smoke prompt is below the 1,024-token caching minimum, so today's data can't show a cache effect. Success-rate and spend queries don't filter by policy yet.
- **Improve:** Run one `--debug` smoke call to confirm the field is accepted and `cached_tokens` is reported as 0. Add the policy filter to the outcome and spend queries before any public comparison. Design a deliberate repeated-prefix workload (≥ 1,024 tokens) for a later warm-versus-uncached experiment.

