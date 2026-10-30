# Step 012 — Implementation report

Prompt: `012-first-real-provider.md`.

## What changed

- **`openai_provider.py` (new):** `OpenAIProvider`, the first real provider. It calls the OpenAI **Responses API** using only the standard library (`urllib` plus a small SSE parser), translates the stream into text chunks plus a final `Usage`, and maps errors to the Step-011 categories. The generic provider interface is unchanged.
- **`real_smoke.py` (new):** `python -m llm_metrics.real_smoke`, the only code path that spends money. It needs `OPENAI_API_KEY`, makes exactly one attempt, and stores it as `environment = 'prod'`.
- **`benchmark.py` (new):** `run_attempt` (price lookup *before* the call, then measure and save) and `print_summary`, shared by the simulated CLI and `real_smoke`. `__main__.py` now uses it. The summary also prints the rates used.
- **`pricing.py`:** adds `("openai", "gpt-6-luna")` at $0.10 / $0.50 per 1M, plus `PRICE_PROVENANCE` (source, verification date; **`None` = unverified**).
- **`storage.spend_by_model()`** for the spend view, computed at query time.
- **Dashboard:**
  - every page carries a data label (TEST / SIMULATED DATA in orange, or REAL PROVIDER DATA in blue);
  - `/requests?data=simulated|real`;
  - new **`/spend`**: Benchmark API Spend for real data only.
- **Config:** the `APP_ENV=prod` refusal message now points to `real_smoke`. `./run.sh` stays simulated-only.
- **Docs:** README section "Real provider (one paid request)", `PROJECT_STATUS.md`, `llm_metrics/README.md`, and `DECISIONS.md` (D008, D009, D038, D040 revised; D043–D045 added).

## Choices made

**Asked before implementing (your answers):**

| Question | Options offered | Chosen |
|---|---|---|
| Official OpenAI pages and API are blocked in this environment, and there's no key. How to handle pricing provenance and the smoke call? | (a) implement; rates marked unverified; you verify and run the smoke call; (b) you allow the hosts and set a key, then I verify and run it here; (c) commit no real price until verified | **(a)** |
| HTTP client | (a) standard library `urllib` + SSE parser; (b) official `openai` SDK, pinned (needs pip in `.venv`, revising D012) | **(a) standard library** |
| OpenAI API | (a) Responses API (`/v1/responses`, usage in `response.completed`); (b) Chat Completions with `stream_options.include_usage` | **(a) Responses API** |
| How real runs fit the environments | (a) separate explicit command, rows stored as `prod`, `./run.sh` stays simulated; (b) `APP_ENV=prod ./run.sh` makes a paid call | **(a) separate command** |

**Made during implementation (with reasons):**

- **Auth and request errors (HTTP 400/401/403/404) aren't recorded attempts.** They mean our key, access or parameters are wrong, which says nothing about provider reliability. Recording them would distort the success rate. They raise `RequestRejected`, and `real_smoke` exits 2 with "Nothing was recorded".
- **`response.incomplete` with reason `max_output_tokens` counts as success.** Hitting the requested cap is expected, and the usage is authoritative. Other incomplete reasons (e.g. content filter) map to `provider_error`.
- **`error` events:** a code containing `rate_limit` maps to `rate_limited`; anything else maps to `provider_error`.
- **Timeout:** 60 s for connect and for each socket read (`TIMEOUT_S`). There's no overall deadline, so a stream that keeps trickling could exceed 60 s in total.
- **`store: false`**, so OpenAI doesn't retain the response. No tools, and no reasoning parameter: I couldn't verify gpt-6-luna's supported reasoning settings, and an unsupported parameter would fail the request.
- **Smoke prompt:** "Reply with one short friendly sentence greeting a benchmark tool." It's fixed, harmless and text-only, and it's never printed.
- **No confirmation flag;** running the command is the opt-in. It prints "About to make exactly ONE paid API request: …" (and a warning while the price is unverified) before calling.
- **Price lookup before the call,** so an unknown model fails without spending money.
- **Spend page defaults to 30d** (the aggregate default stays 7d), because spend accumulates slowly.
- **Spend sums only successful attempts' stored costs.** Failed attempts are counted in a separate column. A group with only failures shows **"unknown"**, never $0. The grand total sums known costs only.
- **Data selector** on `/requests` (`data=simulated|real`), so the real smoke result is inspectable without mixing populations. Invalid or repeated values return 400, as for window and metric.
- **Network isolation in tests:** a fake opener is injected via the constructor, and a `no_network` decorator patches `socket.socket.connect` and `urllib.request.urlopen` to fail. An import test runs in a fresh process with sockets disabled; I avoided `importlib.reload`, which made test order matter.
- **`OpenAIProvider.__repr__`** hides the key; the key exists only in the `Authorization` header.

## Exact provider / model / API path

- `POST https://api.openai.com/v1/responses`, with headers `Authorization: Bearer $OPENAI_API_KEY`, `Content-Type: application/json` and `Accept: text/event-stream`.
- Body: `{"model": "gpt-6-luna", "input": <fixed prompt>, "max_output_tokens": 64, "stream": true, "store": false}`.
- Events used:
  - `response.output_text.delta` (`delta`) gives text chunks;
  - `response.completed` (`response.usage.input_tokens`, `output_tokens`) gives `Usage`;
  - `response.incomplete` (reason `max_output_tokens`) also gives `Usage`;
  - `response.failed` and `error` are failures;
  - all other events are ignored.
- **Not verified against live API docs** (unreachable from this environment). The event names follow the documented Responses API streaming format as I know it; confirm with the first smoke run.

## Dependency choice

None added. The standard library keeps `./run.sh` and the Chromebook setup unchanged (`.venv` has no pip, D012). It also avoids SDK default retries, which would break "one attempt = one call", and keeps error mapping explicit. The cost is ~150 lines of HTTP, SSE and error handling that we own and test.

## Pricing source, verification, effective rates

- **Provider / model / tier:** OpenAI `gpt-6-luna`, standard tier (synchronous API; not batch, priority or cached-input rates).
- **Rates stored:** $0.10 per 1M input tokens and $0.50 per 1M output tokens, written to every request row.
- **Official source:** https://openai.com/api/pricing/. **NOT VERIFIED.** On 2026-10-30, `openai.com`, `developers.openai.com` and `platform.openai.com` were blocked by the implementation environment's network policy.
- **What the rate is based on:** the Step 012 prompt, and agreement across third-party trackers checked on 2026-10-30 ([getdeploying](https://getdeploying.com/llms/gpt-6-luna), [eesel.ai](https://www.eesel.ai/blog/gpt-6-luna-pricing), [developersdigest](https://www.developersdigest.tech/models/gpt-6-luna), [llmbase](https://llmbase.ai/models/openai/gpt-6-luna/)). Those sources also cite cached input at $0.01/1M and batch at $0.05 / $0.25, neither of which is used.
- **Flagged in code:** `PRICE_PROVENANCE[("openai", "gpt-6-luna")] = (source, None)`, and `real_smoke` prints a warning while the price is unverified.
- **To verify:** check the official page, then set the date in `PRICE_PROVENANCE`, update the comment in `pricing.py`, the README, and this report's status.

## Tests / run

- **147 tests, OK on Python 3.13 and 3.11** (~21 s). Zero network: fake openers, blocked sockets, and a no-network subprocess import test.
- **New adapter and smoke tests (21):**
  - stream translation; the request body (cap 64, model, `store: false`, no tools, one call, timeout);
  - cap-reached `incomplete` as success;
  - 8 malformed or missing usage cases, all `invalid_response` with no fabricated tokens;
  - HTTP 429, 5xx, 408/504, URL, connection and timeout errors, mid-stream timeout and reset, and error events mapped to categories;
  - 400/401/403/404 raise `RequestRejected`; programming errors propagate;
  - the key isn't in `repr`, messages, printed output or DB bytes, and neither are the prompt and response;
  - price and cost (20 in + 15 out = $0.0000095), and provenance flagged unverified;
  - `real_smoke` refuses without a key, in-process and as a subprocess, with no DB created;
  - a successful smoke run is stored as `prod`, has no "(simulated)" label, and doesn't print the prompt;
  - a 401 is not recorded;
  - the simulated CLI makes no network calls.
- **Spend tests:** grouping by provider + model, failure-only groups as unknown (not $0), simulated costs excluded, the window filter, grand total and rendering, and labels.
- **Data selector tests;** routes and 400s.
- **Clean `./run.sh`:** simulated output now also prints the `Rates:` line; `/spend`, `/requests?data=real`, `/requests` and `/` all return 200. `APP_ENV=prod ./run.sh` exits 2 with the new message, and the real database has 0 `prod` rows.

## Real smoke call

**Not run.** There was no `OPENAI_API_KEY` in the implementation environment, and `api.openai.com` is blocked by its network policy (proxy 403). There are no real measurements to report. To run it (one paid call, roughly a few millionths of a dollar at the listed rates):

```bash
export OPENAI_API_KEY=...
python3 -m llm_metrics.real_smoke
```

## Failure mapping (provider boundary)

| Source | Category |
|---|---|
| HTTP 429; `error` event with a `rate_limit` code | `rate_limited` |
| HTTP 408, 504; `TimeoutError` / `socket.timeout` on connect or read | `timeout` |
| Other HTTP 5xx; `response.failed`; other `error` events; `response.incomplete` not caused by the cap | `provider_error` |
| `URLError`, connection refused/reset, `OSError`, `HTTPException` | `transport_error` |
| Event not JSON or not an object; non-text delta; final event without valid non-negative integer usage; non-UTF-8 stream; (in measurement) no text, missing/duplicate usage | `invalid_response` |
| HTTP 400, 401, 403, 404 and other 4xx | not an outcome: `RequestRejected`, nothing recorded |
| Any other exception | an llm-metrics bug; propagates, nothing recorded |

No messages, bodies, prompts, keys or stack traces are stored.

## Benchmark-spend semantics

- **Population:** `requests` rows with `environment = 'prod'` (real attempts) and `now − window <= recorded_at <= now` (inclusive), grouped by the stored `provider` and `model`.
- **Per group:**
  - `successful paid calls` = successes;
  - input tokens, output tokens and total cost = sums over successful attempts' stored values;
  - `failed attempts (cost unknown)` = count of failures.
  A group with no success shows "unknown" cost and "—" tokens.
- **Grand total:** sums of calls and tokens, and the sum of known costs only. Ordered by cost, highest first.
- **Excludes** simulated data (`test`), infrastructure and hosting costs, and any billing for failed calls (unknown).
- **No materialized aggregates;** the raw request rows are the source of truth.

## Known limitations / review questions

1. **Price unverified.** Please check https://openai.com/api/pricing/ and confirm $0.10 / $0.50 for `gpt-6-luna` standard tier.
2. **Event format unverified** against live API docs; the first smoke run will confirm it. If usage arrives in a different shape, the attempt is recorded as `invalid_response` rather than inventing numbers.
3. **Reasoning tokens:** if `gpt-6-luna` spends hidden reasoning tokens, a 64-token cap might be exhausted before visible text. That would be recorded honestly (possibly `invalid_response`: no text). Should we set a minimal reasoning effort once verified?
4. **Cost model:** cached-input discounts aren't modelled (the prompt is tiny, so caching is unlikely); reasoning tokens are billed as output via OpenAI's `output_tokens`.
5. **Unknown billing on failures:** a failed call may still have been billed; spend shows it as unknown.
6. **Timeout:** 60 s per socket operation, not an overall deadline.
7. **Shared-network caveat (applies once this runs in the cloud):** sessions need `api.openai.com` allowed; on your Chromebook, normal internet access is enough.

## Design Q&A

**Why the standard library instead of the official SDK?** One small endpoint and a simple SSE stream don't justify a dependency that would force pip into `.venv` (D012) and bring default automatic retries. Retries would silently turn one attempt into several calls and corrupt both the success rate and spend. Owning about 150 lines gives explicit, tested error mapping. *Tradeoff:* we must track API changes ourselves, with no typed models.

**Why are auth and bad-request errors not recorded as failed attempts?** The success rate measures the provider's reliability under our workload. A 401 or 404 measures *our* configuration. Recording them would let a typo in the key make OpenAI look 0% available. Server-side and transport errors are recorded, because those reflect the provider and the path to it.

**Why is spend computed only from successful attempts, and why show "unknown" instead of $0?** Request cost is defined from authoritative usage, which only successful attempts have. A failed attempt may or may not have been billed; writing $0 would understate spend and violate the Step-011 unknown-versus-zero rule. Counting failures next to the spend keeps the uncertainty visible.

## Follow-up: first live call failed (2026-10-30)

The owner's first manual run printed `Outcome: FAILED — Provider/server error (provider_error)`, `Failed after: 5425.6 ms`, attempt `6a39b71e…`. No further real call was made from the implementation environment, which can't reach OpenAI anyway.

**Diagnosis.** Only four adapter paths can produce `provider_error`, and the original code discarded everything that would distinguish them:

1. HTTP status ≥ 500 (not 504) when opening the request;
2. a `response.failed` stream event;
3. an `error` stream event whose code isn't a rate limit;
4. `response.incomplete` with a reason other than `max_output_tokens`.

Measurement itself never produces `provider_error`; 4xx errors raise `RequestRejected` and aren't recorded; hitting the cap is a success (or `invalid_response` if there's no text). The 5.4 s suggests the stream started and then failed (paths 2–4), but a slow 5xx (path 1) is possible. Also relevant: without a `reasoning` setting, gpt-6-luna reportedly defaults to **medium** reasoning effort, so hidden reasoning tokens were competing with the 64-token cap.

**Change (minimal):**

- `ProviderFailure` and `RequestRejected` now carry sanitized `diagnostics`: the failing path, HTTP status, `x-request-id`, OpenAI error `code`/`type`/`param` (from stream events, or from an HTTP error body read with a 64 KB limit and then discarded), the incomplete reason, and the exception class. Each value must match `[A-Za-z0-9_.:-]{1,100}`, otherwise it shows as `<redacted>`.
- `measure_request` passes them through the in-memory attempt as `diagnostics`. That isn't a storage column, and a test checks they never reach the database file.
- `python -m llm_metrics.real_smoke --debug` prints them to stderr after a failed or rejected attempt. Without `--debug`, nothing new is printed. Unknown arguments are refused before any request.
- The request body adds `"reasoning": {"effort": "none"}`.
- `PRICE_PROVENANCE` for `gpt-6-luna` is now verified on 2026-10-30 (by the owner); the "not yet verified" warning no longer prints.
- The stored outcome remains `provider_error`. Still one attempt, no retry, no SDK.

**Tests:** 156, OK on Python 3.13 and 3.11. New: each `provider_error` path reports which path it was, with the expected sanitized fields; free-text code/param values are redacted; the key, `Bearer`, the prompt, response text and error messages never appear in diagnostics or output; a 400 rejection reports `error_param` (e.g. `reasoning.effort`); diagnostics aren't stored; `--debug` controls printing; unknown arguments are refused with no request; the request body includes the reasoning setting.

**Choices made:**

- **Asked by you (in the follow-up request):** keep the outcome `provider_error`; add sanitized status, error code and request id; set the verified price; set `reasoning.effort="none"` if officially supported; make no further real calls.
- **Made by me:**
  - **Opt-in `--debug` flag** rather than always printing diagnostics, to keep normal output unchanged.
  - **A token allowlist** (`[A-Za-z0-9_.:-]`, max 100) instead of a denylist: anything resembling free text is redacted, so a message can't leak through a code field.
  - **Reading the HTTP error body** (≤ 64 KB) only to extract `code`/`type`/`param`. You said not to print arbitrary bodies; those three fields are identifiers, not body text.
  - **Including `error_param`,** which names the parameter OpenAI objected to. That's the fastest way to see whether `reasoning.effort` is rejected.
  - **Setting `reasoning.effort="none"` despite only third-party confirmation:** the official docs are blocked here, and the third-party sources cite OpenAI's documentation. If it's unsupported, the API returns 400 (not recorded, likely not billed), and `--debug` names the param.
  - **Owner verification of the price** recorded as `"2026-10-30"` in `PRICE_PROVENANCE`.

**Next manual step (yours):** run exactly once:

```bash
python3 -m llm_metrics.real_smoke --debug
```

Then share the printed `Debug (sanitized, not stored): …` line.
