# Step 016 — Implementation report: four-provider benchmark adapters

Status: implemented, pending review. No paid or network call was made by the implementation or the tests.

> **Comparability statement.** The four-provider benchmark controls workload content, workload version, output cap, measurement origin and known request settings. It does not establish that the selected models have identical capability, tokenizer behavior, internal architecture, reasoning implementation, caching implementation or service infrastructure. Performance results therefore describe **observed behavior of these exact provider/model/request-profile combinations under this benchmark methodology**. They are not universal provider performance claims.

## 1. Files and modules changed

New:
- `llm_metrics/targets.py`: `RequestProfile`, the four benchmark targets plus the simulated profile, `get_target`, and `get_profile`. Imports nothing from the package.
- `llm_metrics/http_streaming.py`: behavior that is identical for every adapter.
  - Sends one request with no retry.
  - Maps open and read errors to failure categories.
  - Parses SSE.
  - Sanitizes values with `safe` and `safe_id`.
  - Provides the `RequestRejected` base class.
- `llm_metrics/anthropic_provider.py`, `google_provider.py`, `xai_provider.py`: the three new adapters.
- `llm_metrics/real_benchmark.py`: the explicit one-request pilot command.
- `tests/test_real_providers.py`: protocol fixtures and adapter tests (30 tests).
- `tests/test_targets.py`: registry, profiles, pricing, enforcement, and the pilot command (27 tests).
- `design-questions/16/`: four role files.

Changed:
- `openai_provider.py`: refactored onto `http_streaming`. Its body is now built from `targets.OPENAI` and the wire request is identical.
- `providers.py`: adds a `request_profile` attribute; the dummy declares `targets.SIMULATED`.
- `benchmark.py`:
  - Profile checks.
  - Price-tier guard.
  - Cached-rate cost.
  - Stores `request_profile_id` and `cached_input_price_per_1m`.
  - Summary line "Request profile", plus a cached-rate line when one applies.
- `pricing.py`: `Price.cached_input_per_1m` and `max_input_tokens`; three new prices; cached-aware `request_cost`.
- `storage.py`: schema v7 with columns `request_profile_id` and `cached_input_price_per_1m`. The profile is required for new attempts, and the upgrade keeps old rows NULL.
- `real_smoke.py`: takes its model id from `targets.OPENAI`.
- Tests:
  - Existing request fixtures gain `request_profile_id`.
  - The OpenAI tests expect the shared `TIMEOUT_S` and the new `Price` fields and verification date.
  - Schema version is 7, with new v6→v7 upgrade and required-profile tests.
  - Layering and no-Flask lists include the new modules.
- Docs: `DECISIONS.md` (D062–D064; D004, D038 and D044 annotated), `PROJECT_STATUS.md`, `README.md`, `llm_metrics/README.md`, `prompts/chatgpt-conversation.md`, `design-questions/README.md`.

Unchanged: `workloads.py`. `interactive-chat-v1` is byte-for-byte identical, and the SHA-256 golden tests pass. Dashboard, API, templates and analytics are also unchanged.

## 2. Selected provider/model table

| Provider | Model | Why this model |
|---|---|---|
| OpenAI | `gpt-6-luna` | The existing target (Steps 012–015). Small and inexpensive, with reasoning that can be turned off. It is kept so the live-validated path stays the reference. |
| Anthropic | `claude-haiku-5-5` | Anthropic's "fastest" current model, "for high-volume, latency-sensitive tasks". Current and GA (released 2026-10-07, active). Accepts `thinking: disabled`. |
| Google | `gemini-3.5-flash-lite` | Stable, "fastest, most cost-effective 3.5 model". Its thinking defaults to and can be pinned at `minimal`. The alternative `gemini-3.8-flash` (stable, defaults to medium thinking, and minimal is not offered) would reason more on an interactive request, so I chose the smallest defensible option. |
| xAI | `grok-4.20-0309-non-reasoning` | The only current xAI text model with explicit reasoning off ("Reasoning: No"). The flagship `grok-4.7` and 4.6/4.5 always reason ("Reasoning cannot be disabled"). Listed in the current pricing table with no deprecation notice. |

These are not equal-capability models. Each is its provider's small or fast tier with the least hidden reasoning available.

## 3. Exact model IDs

`gpt-6-luna`, `claude-haiku-5-5`, `gemini-3.5-flash-lite`, `grok-4.20-0309-non-reasoning`. Each is defined once in `llm_metrics/targets.py` and once in `pricing.py`; a test checks that no other module contains them.

## 4. Request-profile table

Fields not listed are not sent and take the provider default. No temperature, top_p, top_k, system prompt, instructions or tools are sent to any provider.

| Profile id | Output-cap field | Settings sent (beyond model, prompt, cap, `stream: true`) | Reasoning | Cache policy | Key variable |
|---|---|---|---|---|---|
| `openai.gpt-6-luna.v1` | `max_output_tokens` | `store: false`, `reasoning.effort: "none"`, `prompt_cache_options.mode: "explicit"` | effort none (off) | `disabled` | `OPENAI_API_KEY` |
| `anthropic.claude-haiku-5-5.v1` | `max_tokens` | `thinking.type: "disabled"`; header `anthropic-version: 2023-06-01` | thinking off; `output_config.effort` not sent (default `medium`) | `provider_default` | `ANTHROPIC_API_KEY` |
| `google.gemini-3.5-flash-lite.v1` | `generation_config.max_output_tokens` | `store: false`, `generation_config.thinking_level: "minimal"` | minimal (lowest; not fully off) | `provider_default` | `GEMINI_API_KEY` |
| `xai.grok-4.20-0309-non-reasoning.v1` | `max_output_tokens` | `store: false` | non-reasoning model; no field sent | `provider_default` | `XAI_API_KEY` |
| `dummy.dummy-model-v1.v1` | (simulated) | none | n/a | `provider_default` | none |

The request profile is stored per attempt. Any change to the model, endpoint or a setting requires a new profile version, and tests pin all four profiles.

**Interface change, and why.** The provider contract `stream(prompt, max_output_tokens)` is unchanged.
- **Why the old contract was not enough:** it said nothing about which request settings produced a measurement. Step 015 flagged this.
- **Smallest new concept:** one class attribute, `request_profile`. It belongs at the provider-neutral layer because `benchmark` must store it and verify that it agrees with `name`, `model` and `cache_policy`.
- **Compatibility:**
  - The dummy declares `SIMULATED`.
  - OpenAI declares `OPENAI`, and its body is unchanged (same test fixture).
  - Providers without a profile still stream but cannot be benchmarked.

## 5. API endpoint and protocol per provider

| Provider | Endpoint | Auth | Request representation |
|---|---|---|---|
| OpenAI | `POST https://api.openai.com/v1/responses`, SSE | `Authorization: Bearer` | `input`: the prompt string |
| Anthropic | `POST https://api.anthropic.com/v1/messages`, SSE | `x-api-key`, `anthropic-version: 2023-06-01` | `messages: [{role: "user", content: prompt}]` (the smallest neutral wrapper; no system prompt) |
| Google | `POST https://generativelanguage.googleapis.com/v1beta/interactions?alt=sse`, SSE | `x-goog-api-key` (never in the URL) | `input`: the prompt string |
| xAI | `POST https://api.x.ai/v1/responses`, SSE | `Authorization: Bearer` | `input`: the prompt string |

For Google, I used the Interactions API. Google's docs recommend it "for all new development" and label `generateContent` as legacy ("remains fully supported"). It stores interactions by default, so `store: false` is sent.

## 6. Streaming event mapping (what counts as output)

TTFT is unchanged: it runs from just before the request until the first text item the adapter yields. Only these events yield text:

| Provider | Output events | Ignored (never first content) | End of a complete response |
|---|---|---|---|
| OpenAI | `response.output_text.delta` | `response.created`, item and part events, others | `response.completed`; `response.incomplete` with reason `max_output_tokens` |
| Anthropic | `content_block_delta` with `delta.type == "text_delta"` | `message_start`, `content_block_start/stop`, `ping`, `thinking_delta`, `signature_delta` | `message_stop` after stop reason `end_turn`, `max_tokens` or `stop_sequence` |
| Google | `step.delta` with `delta.type == "text"` | `interaction.created`, `interaction.status_update`, `step.start/stop`, thought steps (`thought_summary`, `thought_signature`) | `interaction.completed` with status `completed`, or `incomplete` that reached the cap |
| xAI | `response.output_text.delta` | `response.created`, item and part events, reasoning events | `response.completed`; `response.incomplete` with reason `max_output_tokens` |

Any other stop is a `provider_error`, with its sanitized reason in `--debug` diagnostics. This covers Anthropic `refusal`, Gemini incomplete below the cap, and xAI `content_filter`. A stream that ends without its final event yields no usage and is recorded as `invalid_response`.

## 7. Usage mapping

| Provider | `input_tokens` (whole prompt) | `cached_input_tokens` (NULL if absent) | `output_tokens` (billed, incl. reasoning) |
|---|---|---|---|
| OpenAI | `usage.input_tokens` | `usage.input_tokens_details.cached_tokens` | `usage.output_tokens` |
| Anthropic | `input_tokens + cache_read_input_tokens + cache_creation_input_tokens`. `message_start` and cumulative `message_delta` are merged, and the last value wins. Anthropic's `input_tokens` excludes cache. | `cache_read_input_tokens` | `output_tokens` (cumulative, from the last `message_delta`) |
| Google | `usage.total_input_tokens` | `usage.total_cached_tokens` | `total_output_tokens + total_thought_tokens`. Google bills "the sum of output tokens and thinking tokens", and thoughts count against `max_output_tokens`. An absent thought count is 0 because Google omits zero-valued fields. |
| xAI | `usage.input_tokens` (includes cached) | `usage.input_tokens_details.cached_tokens` | `usage.output_tokens` |

Counts must be non-negative integers, and cached tokens may not exceed input; otherwise the response is `invalid_response`. Measurement still rejects output above the requested cap. Nothing is estimated from characters, and `target_input_tokens` is never used as usage.

## 8. Request-ID mapping

| Provider | `provider_request_id` |
|---|---|
| OpenAI | `x-request-id` response header |
| Anthropic | `request-id` response header (also kept for HTTP error responses) |
| Google | interaction `id` from `interaction.created` / `interaction.completed`. Google documents no request-id header. |
| xAI | response `id` from `response.created` / final events. xAI documents no request-id header. |

Ids are stored only if they are short identifier-like tokens; otherwise the value is NULL, never a redaction marker. Our own `requests.id` stays the primary identity.

## 9. Cache semantics

- **OpenAI** `disabled`: explicit cache mode with no breakpoints, which is documented as no caching and no cache writes.
- **Anthropic** `provider_default`: the Messages API caches only at `cache_control` breakpoints (opt-in). None are sent, so no reuse is expected. Because this is the default rather than a control we send, it is recorded as `provider_default`, per the D052 vocabulary.
- **Google** `provider_default`: implicit caching is "enabled by default for all Gemini 2.5 and newer models", and no per-request off switch is documented. The documented minimum for listed models is 4,096 tokens, and `interactive-chat-v1` is about 2K. This is not established for Flash-Lite.
- **xAI** `provider_default`: prompts are cached automatically, and no off switch is documented. Repeated runs may report cached tokens. They are recorded and priced at the cached rate, never inferred from latency.
- No measurement is called "cold". Cache policies differ across targets, so later analyses must not silently aggregate them; the profile id makes the difference explicit.

## 10. Reasoning and thinking semantics

| Provider | Reasoning on this model | Our setting | Effect |
|---|---|---|---|
| OpenAI | Configurable; default `medium` | `reasoning.effort: none` | Reasoning off |
| Anthropic | Adaptive thinking on by default; Haiku 5.5 accepts `disabled` at effort ≤ high | `thinking: {type: "disabled"}`; effort not sent (default `medium`) | Thinking off |
| Google | Thinking on; levels minimal/low/medium/high; default minimal | `thinking_level: "minimal"` (pinned) | Minimal thinking. Not off; may "reason very minimally" on complex tasks. |
| xAI | Model variant without reasoning | No field sent | Non-reasoning model |

These are four different controls. Only the OpenAI and Anthropic settings are defined by their providers as "off". No prompt was changed to suppress reasoning.

## 11. Pricing and source provenance

All prices are USD per 1M tokens, standard synchronous tier, verified 2026-11-01. They are stored per attempt as `input_price_per_1m`, `output_price_per_1m` and `cached_input_price_per_1m`.

| Target | Input | Output | Cached input | Modelled tier | Source |
|---|---:|---:|---:|---|---|
| `gpt-6-luna` | 0.10 | 0.50 | 0.01 | ≤272K input | https://developers.openai.com/api/docs/pricing |
| `claude-haiku-5-5` | 0.10 | 0.50 | 0.01 (cache read) | prompts ≤100K | https://platform.claude.com/docs/en/models/haiku-5-5/overview |
| `gemini-3.5-flash-lite` | 0.30 | 2.50 (incl. thinking) | 0.03 ("context caching") | one tier | https://ai.google.dev/gemini-api/docs/pricing |
| `grok-4.20-0309-non-reasoning` | 1.25 | 2.50 | 0.20 | <200K prompt | https://docs.x.ai/docs/models (text API pricing) |

**Cost:** (input − cached) × input rate + cached × cached rate + output × output rate.
- If cached tokens are unknown, the standard rate applies to all input; no discount is guessed.
- If cached tokens are reported but no cached rate exists, the cost raises an error rather than charging the wrong rate.

**Not modelled:**
- Long-context tiers. `run_attempt` refuses a workload whose size target exceeds half the tier limit; every catalogue workload passes.
- Anthropic cache writes (none expected, since no `cache_control` is sent).
- Gemini cache storage.
- Batch, flex and priority tiers.

A failed attempt's cost stays unknown (NULL).

Other official sources used:
- **OpenAI:** model page `/api/docs/models/gpt-6-luna` and prompt caching guide (D047, D052).
- **Anthropic:**
  - Models overview: `platform.claude.com/docs/en/about-claude/models/overview`.
  - Thinking: `/build-with-claude/thinking`.
  - Streaming: `/build-with-claude/streaming`.
  - Prompt caching: `/build-with-claude/prompt-caching`.
  - Errors: `/api/errors`.
- **Google:**
  - Models: `ai.google.dev/gemini-api/docs/models` and `/models/gemini-3.5-flash-lite`.
  - Thinking: `/thinking`.
  - Caching: `/caching`.
  - Interactions API reference: `ai.google.dev/api/interactions-api`.
  - Streaming interactions: `/interactions/streaming`.
  - Migration guide: `/migrate-to-interactions`.
  - API errors: `/api-errors`.
- **xAI:**
  - Models and pricing: `docs.x.ai/docs/models`.
  - Reasoning guide: `/docs/guides/reasoning`.
  - Streaming guide: `/docs/guides/streaming-response`.
  - API reference: `/docs/api-reference` (Responses).
  - Prompt-caching usage and pricing: `docs.x.ai/developers/advanced-api-usage/prompt-caching/usage-and-pricing`.
  - Debugging errors: `docs.x.ai/developers/debugging`.

## 12. Failure normalization

| Condition | OpenAI | Anthropic | Google | xAI |
|---|---|---|---|---|
| HTTP 429 | `rate_limited` (unless an account-credit code: rejected) | `rate_limited` | `rate_limited` | `rate_limited` |
| HTTP 408 / 504 | `timeout` | `timeout` | `timeout` | `timeout` |
| Other 5xx | `provider_error` | `provider_error` (incl. 529 overloaded) | `provider_error` | `provider_error` |
| Other 4xx (400/401/402/403/404/...) | rejected, not recorded | rejected, not recorded | rejected, not recorded | rejected, not recorded |
| Connect failure / read reset | `transport_error` | same | same | same |
| Connect or read timeout | `timeout` | same | same | same |
| In-stream rate limit | `error` code containing `rate_limit` | `rate_limit_error` | code containing rate_limit / quota / too_many_requests | code containing `rate_limit` |
| In-stream server error | `response.failed`, `error` | `overloaded_error`, `api_error`, unknown types | other codes | `response.failed`, other codes |
| In-stream timeout | — | `timeout_error` | `deadline` / `timeout` codes | — |
| In-stream account or request error | credit codes → rejected | `billing_error`, `authentication_error`, `permission_error`, `invalid_request_error`, ... → rejected | `payment_required`, `failed_precondition`, `permission_denied`, `authentication`, `invalid`, `not_found` → rejected | none documented |
| Malformed / incomplete stream | `invalid_response` | same | same | same |

**Rejections.** `RequestRejected` subclasses share `http_streaming.RequestRejected`. They mean our key, access, parameters or billing are wrong, so the attempt is not recorded as provider unreliability.

**Diagnostics.** These are sanitized identifiers only: code path, HTTP status, request id, error code/type/status, and stop or incomplete reason. They are shown only with `--debug` and never stored. Error messages, bodies, prompts, responses and keys never appear in diagnostics, exceptions or the database; tests cover this for every adapter. Nothing retries.

## 13. Dependency changes

None. All four adapters use `urllib`, `json` and `http.client` from the standard library.
- **Why no SDKs:** the official SDKs retry by default (Anthropic: twice), which would break "one call = one attempt". They would also add four dependency trees for small SSE parsers that are easy to test.
- **Shared code:** only the behavior that is genuinely identical moved to `http_streaming.py`; each provider's protocol semantics stay in its adapter.
- **Layering:** AST tests check that adapters import no measurement, pricing, storage or other adapters, and that `targets` imports nothing from the package.

## 14. Test and style results

- `.venv/bin/python -m unittest discover -s tests`: **342 tests OK**, 59 new (30 adapter, 27 registry/profile/command, 2 storage).
  - Every adapter is tested against representative mocked fixtures for items 1–13 of the prompt: request shape, cap field, content parsing, metadata-before-output, usage, cached unknown versus zero, request id, malformed streams, rate limit, provider error, transport, timeout, and secret handling.
  - Items 14–36 are covered by `tests/test_targets.py`, `tests/test_storage.py`, the existing OpenAI, workload, run-script and web tests, and a byte comparison.
- `pyink --check`, `isort --profile google --check-only`, and `pylint --rcfile=.pylintrc --disable=inconsistent-quotes` on `llm_metrics tests scripts`: no findings.
- Dependency and layering checks (AST and fresh-process no-Flask tests): pass.
- `env -u OPENAI_API_KEY -u ANTHROPIC_API_KEY -u GEMINI_API_KEY -u XAI_API_KEY LLM_METRICS_PORT=0 timeout 120 ./run.sh`:
  - Offline, with tests passing.
  - One simulated attempt: workload `interactive-chat-v1`, profile `dummy.dummy-model-v1.v1`, 1954 simulated input tokens, cap 300.
  - Dashboard served until the timeout.
- Byte comparison: the 14 HTML and API responses rendered with the clock pinned are identical to Step 015. A database created by Step 015 code upgrades to v7 when the new code opens it.
- `interactive-chat-v1` is byte-for-byte unchanged: `workloads.py` has no diff, and the SHA-256 golden tests pass.

## 15. Paid API calls

**None.**
- Tests use fake openers.
- Network-sensitive tests block `socket.connect` and `urllib.request.urlopen`.
- A fresh-process test imports every provider module with sockets disabled.
- No command was run with a real key; the implementation's only network use was reading official documentation.

## 16. Known limitations

- **Live exercise:** only OpenAI has been called live (one smoke sample). The Anthropic, Google and xAI adapters are verified only against documentation and mocked fixtures. Their first live requests (Step 016a) may reveal protocol details the docs do not state.
- **Undocumented facts the adapters assume:**
  - Whether Gemini Interactions `total_output_tokens` includes thought tokens. The adapter assumes it excludes them, from the billing wording; if it includes them, output is overcounted by the thought count, which is minimal at `thinking_level: minimal`.
  - Gemini `incomplete` has no reason field.
  - xAI error codes and in-stream credit errors are not documented.
  - The Gemini and xAI request ids come from the stream body.
- **429 ambiguity:** Anthropic (monthly spend cap) and Gemini (quota) use 429 both for account caps and rate limits. These cannot be told apart reliably and are recorded as `rate_limited`.
- **Gemini endpoint:** the adapter uses the `v1beta` Interactions endpoint shown in Google's examples (a v1 version is mentioned but not shown).
- **Not equivalent conditions:**
  - Gemini thinking cannot be turned fully off.
  - Only OpenAI disables caching.
  - Anthropic's effort is left at its default.
  - Tokenizers differ (Haiku 5.5's tokenizer counts about 30% more tokens than Haiku 4.5 for the same text).
- **Request ids:** Gemini and xAI failures before the first stream event have none.
- **Pricing gaps:** long-context tiers, cache writes, cache storage and batch, flex or priority tiers are not modelled. Prices are a manual snapshot, and Gemini 3.8 Flash's scheduled 2027 price change shows they move.
- **Product views:** aggregate views, `/api/v1/metrics` and spend do not yet filter by request profile, workload or provider target. The Benchmark API Spend page groups by provider/model, so a new profile version of the same model would share a row.
- **Experiment scope:** no budget guardrail, scheduling or attempt windows. Real spend is limited to one request per manual command.

## 17. Manual commands for the Step 016a pilot

Run from the repository root, one provider at a time, with only that provider's key exported. Each command makes exactly one paid request with `interactive-chat-v1` (about 2K input tokens, at most 300 output tokens) and stores it as `prod`. `--debug` prints sanitized diagnostics if the attempt fails or is rejected.

```bash
# Optional: declare where the runner is (otherwise local / unknown).
export LLM_METRICS_ORIGIN_CLOUD=local LLM_METRICS_ORIGIN_REGION=unknown

export OPENAI_API_KEY=...
python3 -m llm_metrics.real_benchmark --provider openai --workload interactive-chat-v1 --real --debug

export ANTHROPIC_API_KEY=...
python3 -m llm_metrics.real_benchmark --provider anthropic --workload interactive-chat-v1 --real --debug

export GEMINI_API_KEY=...
python3 -m llm_metrics.real_benchmark --provider google --workload interactive-chat-v1 --real --debug

export XAI_API_KEY=...
python3 -m llm_metrics.real_benchmark --provider xai --workload interactive-chat-v1 --real --debug
```

Approximate cost per request at the verified rates, assuming about 2K input and 300 output tokens:

| Provider | Approx. cost |
|---|---:|
| OpenAI | $0.0004 |
| Anthropic | $0.0004 |
| Google | $0.0014 |
| xAI | $0.0033 |

So one request per provider costs well under one cent in total.

Results are visible on `/requests?data=real` and `/spend`, and in the `requests` table: `request_profile_id`, `input_tokens`, `cached_input_tokens`, `output_tokens`, `provider_request_id`, and the stored rates.

## Operator checklist (answerable from stored data and code)

- **Which exact model was called?** `requests.model`, which equals the profile's model.
- **Which exact workload was sent?** `requests.workload_id`, matched to `workloads.py` and its SHA-256 pin.
- **Which request settings were used?** `requests.request_profile_id`, matched to `targets.py`.
- **Was reasoning or thinking enabled?** The profile's `reasoning` field (table in section 10).
- **What was the cache policy?** `requests.cache_policy`, plus `cached_input_tokens`.
- **What output cap was requested?** `requests.requested_max_output_tokens`.
- **Which token counts came from the provider?** All of `input_tokens`, `output_tokens` and `cached_input_tokens` (mapping in section 7).
- **How was TTFT determined?** From request start to the first text delta (section 6).
- **Which pricing rates were applied?** `input_price_per_1m`, `output_price_per_1m` and `cached_input_price_per_1m`.
- **Which provider request ID was returned?** `requests.provider_request_id` (section 8).
