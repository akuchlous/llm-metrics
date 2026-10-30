# Step 012a — Implementation report

Prompt: `012a-live-validation-cleanup.md`.

## Live-validation facts (observed, owner-run, 2026-10-30)

Validation of the real path only. **Not benchmark results.**

| Attempt | Outcome | Observed |
|---|---|---|
| `6a39b71e…` (first) | `provider_error` | failed after 5425.6 ms; no observations |
| `4c20aa94…`, `b113ba9a…`, `f5e67e83…` | `provider_error` | failed after 2157.6 / 1087.2 / 1730.7 ms. `b113ba9a` (`--debug`): HTTP 200, then an in-stream `error` event whose details were nested and not yet read |
| two more `--debug` runs (`1ba931f8…`, `1cd70e04…`) | `provider_error` at the time | Both: HTTP 200, then an in-stream `error` event. The first (`req_8d31bcc50b4b40b58ae702b1305f67de`, 2933.8 ms) showed only `error_type=error` (nested details unread). After the nested-details fix, the second (`req_11df58a8a5f34c0db6c670ac72f79281`, 1226.0 ms) showed `error_code=credit_balance_exhausted`, `error_type=insufficient_quota`: the OpenAI account had no credit. Both rows were deleted from the local database at the owner's request. |
| `44c889cb…` (after credit was added) | `success` | total latency 3880.7 ms, TTFT 3630.3 ms, 36.4 chunks/s, 17 input / 14 output tokens (max 64), cost $0.000009 |

- The four remaining early failures have no stored diagnostics, so their cause is **unconfirmed**. Most likely they are the same credit problem.
- No provider request id was captured for any of these attempts: the column did not exist yet. Nothing was backfilled.

Already committed before this step (`94bf7ac`): account-billing errors (`insufficient_quota`, `credit_balance_exhausted`), whether they arrive as HTTP 429, an `error` event or `response.failed`, raise `RequestRejected` and are not recorded. Remote commit `ee23321` reads the nested details of stream `error` events.

## What changed

- **Traceability (D048):**
  - `Usage` and `ProviderFailure` gain an optional `provider_request_id` (default `None`).
  - `OpenAIProvider` fills it from the `x-request-id` header, for success, stream failures and HTTP 5xx/429/408/504.
  - `measure_request` puts it on the attempt, and `save_request` stores it in the new nullable column `requests.provider_request_id`.
  - Schema version 4 adds the column with `ALTER TABLE ADD COLUMN`; existing rows stay NULL.
  - `real_smoke` prints `Provider request id: …` when it is known.
- **Pricing provenance:** `PRICE_PROVENANCE[("openai", "gpt-6-luna")]` changes from `("https://openai.com/api/pricing/ (standard tier)", "2026-10-30")` to `("https://developers.openai.com/api/docs/pricing (standard tier)", "2026-10-30")`. Rates are unchanged at $0.10 / $0.50. The `pricing.py` comment now says the rates were verified against the official docs.
- **Reasoning (D047):** behavior is unchanged (`reasoning.effort: "none"`). The code comment and docs now cite the official model page instead of third-party docs.
- **Docs:** `DECISIONS.md` (D004, D018, D038, D046 revised; D047, D048 added), `PROJECT_STATUS.md`, `prompts/chatgpt-conversation.md`, README, `design-questions/12a/`.

## Evidence (fetched 2026-10-30; no API calls)

- `https://developers.openai.com/api/docs/models/gpt-6-luna` (the redirect target of `platform.openai.com/docs/models/gpt-6-luna`): "`reasoning.effort` supports `none`, `low`, `medium` (default), `high`, `xhigh`, and `max`." It lists the price as $0.1 input / $0.5 output.
- `https://developers.openai.com/api/docs/pricing`, gpt-6-luna standard tier (short context): $0.10 input, $0.01 cached input, $0.50 output per 1M.
- `https://openai.com/api/pricing/` returned HTTP 403 to automated reads, so the provenance now points to the documentation page above.

## Choices made

- **Which provider id:** `x-request-id`, not the response's `resp_…` id.
  - It exists on HTTP errors too.
  - It's the id OpenAI support uses.
  - With `store: false`, a response id can't be looked up later.
- **Carried on the final stream item and on the failure,** not on a provider attribute or a new stream item. The provider stays stateless, and the chunk/TTFT logic doesn't change.
- **Unsafe header values are stored as NULL,** not `<redacted>`. Only short `[A-Za-z0-9_.:-]` tokens are kept, the same rule as diagnostics. A redaction marker isn't an id.
- **Diagnostics stay never-stored.** The stored id has its own field, so D046's "diagnostics are never stored" rule is unchanged.
- **Not shown on the dashboard.** It's stored and printed by `real_smoke`, which is enough for tracing without adding a column to the requests table.
- **Not backfilled.** Ids printed in earlier terminal output are left out of the database. Only values captured by code at request time are stored.
- **`save_request` treats `provider_request_id` as optional** (default `None`), so simulated callers and existing tests don't change.

## Preserved

One provider call per attempt, no retries, `max_output_tokens = 64`, provider-authoritative usage, cap stored separately, failures kept out of success distributions, separate `failed_after_ms`, `./run.sh` simulated-only, real calls only via `real_smoke`, and tests offline. No scheduler, loop or budget cap was added. The `$10/day` project budget is recorded in the direction log for when hosting/scheduling arrives.

## Tests

169 tests, OK on Python 3.13 (3.11 is not installed here). New or changed tests:

- The provider request id is carried and stored on success, and differs from our UUID.
- It is carried on `error`, `response.failed`, invalid-usage and HTTP 5xx failures.
- It is NULL when the stream ends without a final event, when the header is missing or unsafe, and on connection failures.
- The summary prints it.
- A version-3 database upgrades to version 4, keeping rows with a NULL id; re-upgrading is a no-op.
- The schema version is 4.
- The price provenance points to the official docs URL and is verified.
- The measurement dict includes `provider_request_id`.

Existing tests still cover the rest: sanitized diagnostics expose no key, prompt, response text or messages; diagnostics are never stored; the request body includes `reasoning.effort: none`; and the network is blocked in tests.

`./run.sh` (APP_ENV unset, `OPENAI_API_KEY` unset): tests passed, history present, and one simulated attempt saved; the dashboard served until stopped. The local `data/llm_metrics.db` was upgraded to version 4 with all rows kept.

**No paid API call** was made by the implementation or tests in this step.

## Remaining limitations

- One live success is not a benchmark. There's no methodology, no repeated runs, and no confidence interval yet.
- The four early `provider_error` rows remain, and their cause is unconfirmed.
- The provider id is NULL for pre-012a rows, connection failures, and failures detected only by measurement.
- There's no overall attempt deadline, and no hosted budget guardrail yet.

## Design Q&A

**Why store the provider's id at all, if ours is the identity?** Ours makes every attempt traceable inside llm-metrics. The provider's id is the only handle OpenAI accepts when we ask what happened to one specific request. Keeping it as a nullable attribute, never a key, means a provider without ids, or a failure before any response, loses nothing.

**Why is an out-of-credit error not a failed attempt?** The success rate measures the provider as our runner sees it. An empty account measures us, so recording it as `provider_error` would have made OpenAI look less reliable than it was (four of five real attempts).
