# Step 017 — Implementation report: codebase simplification and reuse

Status: implemented, pending review. This was a behavior-preserving cleanup, and no paid or network provider call was made.

## 1. Summary

- **Provider library:** LiteLLM was evaluated against the exact Step 016 contract and **not adopted** (end state **C**: the direct adapters are kept). It would turn "unknown" usage into 0, make network calls at import, and change two request profiles' endpoints. It also carries a recent supply-chain compromise and a large dependency tree.
- **Deduplication:** behavior that was genuinely repeated in the four adapters moved into three small helpers in `llm_metrics/http_streaming.py`:
  - `status_failure`: the HTTP status mapping.
  - `checked_usage`: usage-count validation.
  - `StreamContext`: response identification, request-id capture, read-error mapping, and failure enrichment.
- **Paid commands:** `real_smoke` now delegates to the shared `real_benchmark.run`, so the two paid commands have one refusal, announce, attempt and report path.
- **Removed:**
  - the unused `OpenAIProvider(model=...)` override;
  - the `real_smoke.MODEL` constant;
  - a redundant cache-policy check in `run_attempt` that profile matching already covers;
  - four copies of identical closures, `except` blocks and status mappings.
- **Tests:** fakes (`sse`, `FakeResponse`, `FakeOpener`, `no_network`, `FAKE_KEY`, `SECRETISH`) are consolidated in `tests/fakes.py`. New tests cover no retry, no fallback or substitution, and the shared helpers.
- **Storage:** SQLAlchemy Core + Alembic is **recommended for the next persistence step**, not adopted now.
- **Coding guideline:** the reuse-first principle was already in `CODING_GUIDELINES.md` (design guidance and review checklist, commit `fba39eb`), with the required wording. It was verified, not changed.

## 2. Duplicate-code audit

| Pattern | Where | Classification | Action |
|---|---|---|---|
| HTTP status → category (429/408/504/5xx/else reject) | 4 adapters' `_failure_for_status` | meaningful duplication | `http_streaming.status_failure`. Adapters keep only their own diagnostics and account-error checks. |
| `stream_info` dict, `failure()` closure, `except ProviderFailure` enrichment | 4 adapters' `stream()` | meaningful duplication | `http_streaming.StreamContext` (`failure`, `reading`, `set_request_id`) |
| Read-error mapping (timeout/transport/decode) | 4 adapters (already shared in 016 via `read_failures`) | meaningful duplication | merged into `StreamContext.reading` |
| Count validation + cached ≤ input | OpenAI, xAI, Google `_usage` | meaningful duplication | `http_streaming.checked_usage` (Anthropic also uses it) |
| Key check, announcement, attempt, rejection, debug printing | `real_smoke.main` and `real_benchmark.main` | meaningful duplication | `real_benchmark.run`; `real_smoke` is a 42-line wrapper |
| `OpenAIProvider(model=...)` | adapter + smoke | obsolete path (the profile fixes the model; `run_attempt` refused any other) | removed |
| Cache-policy validity check in `run_attempt` | benchmark | duplicate validation (profile match + tested profiles + DB CHECK) | removed |
| Fake HTTP plumbing (`sse`, `FakeResponse`, `FakeOpener`, `no_network`) | 3 test files | meaningful test duplication | `tests/fakes.py` |
| Event dispatch, usage field names, request-id source, error-code tables, request bodies | each adapter | intentional duplication: provider contracts differ | kept |
| OpenAI vs xAI Responses parsing | 2 adapters | intentional: similar shape, but different account errors, id source, settings and documentation | kept separate |
| `sse_events`, `open_stream`, `safe`/`safe_id`, `post_json` | already shared (016) | — | unchanged |
| Hand-written CLI parsing (`__main__`, `real_benchmark`) instead of `argparse` | 2 commands | incidental similarity. `argparse` would echo unknown arguments, such as a pasted key, to stderr and exit through `SystemExit`. | kept |
| `percentiles.nearest_rank` | analytics | incidental: stdlib `statistics.quantiles` does not do nearest-rank | kept |
| OpenAI-specific tests overlapping the generic adapter tests | tests | test duplication worth keeping: OpenAI is the live-validated baseline with detailed diagnostics tests | kept |
| Storage row construction / query SQL | `storage.py` | intentional: constant SQL per query, no generic builder | kept (see D066) |
| Dashboard/API formatting | `dashboard.py` / `api.py` | intentional: human formatting vs JSON facts (D059/D060) | kept |

## 3. LiteLLM evaluation (in-process library; proxy not considered)

Sources, checked 2026-11-01:
- LiteLLM source: `litellm/__init__.py`, `litellm_core_utils/get_model_cost_map.py`, `litellm_core_utils/streaming_handler.py`.
- LiteLLM docs: `docs.litellm.ai/docs/completion/stream`, `/completion/reliable_completions`, `/providers/gemini`, `/providers/xai`.
- PyPI incident reporting (pureai.com, 2026-03-25).

| Requirement | OpenAI `gpt-6-luna` | Anthropic `claude-haiku-5-5` | Google `gemini-3.5-flash-lite` | xAI `grok-4.20-0309-non-reasoning` |
|---|---|---|---|---|
| 1 Exact model selection | yes | yes | yes | yes |
| 2 Streaming | yes | yes | yes | yes |
| 3 Exact prompt text | yes (as a chat message) | yes | yes | yes |
| 4 Output-cap mapping | yes (`max_tokens`/`max_completion_tokens` mapping) | yes | yes | yes |
| 5 LiteLLM retries off | `num_retries` defaults to None; a `fallbacks` param exists. Needs proof per call. | same | same | same |
| 6 SDK retries off | Uses the OpenAI SDK underneath, which retries by default unless overridden. Not proven for LiteLLM's path. | Anthropic path not proven | n/a (HTTP) | via OpenAI-compatible client; not proven |
| 7 No fallback/routing | only if never configured; stream-fallback logic exists in the wrapper | same | same | same |
| 8 First text visible for TTFT | yes (delta content) | yes | yes | yes |
| 9–10 Authoritative input/output | only if usage is reported. **When unreported, the wrapper records `UnreportedUsage(prompt_tokens=0, completion_tokens=0)`**: a fabricated zero. | same | same | same |
| 11 Cached tokens, unknown ≠ 0 | normalized into `prompt_tokens_details`; absence handling not guaranteed | cache read/creation re-mapped | re-mapped | not documented |
| 12 Provider request id | not exposed by our current `x-request-id` contract without `_hidden_params` digging (unverified) | same (`request-id`) | ours is the interaction id: **not available**, wrong API | ours is the Responses id: **not available**, wrong API |
| 13 Cache controls of the profile | `prompt_cache_options` would need `extra_body` | no `cache_control` sent: ok | implicit default: ok | default: ok |
| 14 Reasoning settings of the profile | `reasoning_effort` maps to chat completions, **not the Responses API** of `openai.gpt-6-luna.v1` | `thinking` passthrough possible | maps to `generateContent` `thinking_level`; **some Flash models get `minimal` rewritten to `low`** | n/a |
| Endpoint of the request profile | chat completions / responses bridge, not our profile's endpoint | Messages: ok | **`generateContent`, not the Interactions API** (profile endpoint changes) | **chat completions, not Responses** (profile endpoint changes) |
| 15 Failure info for categories | mapped to LiteLLM exception classes; our account-vs-provider distinctions (e.g. `insufficient_quota` in a 200 stream) need re-derivation | same | same | same |
| 16 No prompt/response/error logging | off by default (callbacks empty) | same | same | same |
| 17 No hidden network/telemetry | **fetches its model price map from GitHub at import** unless `LITELLM_LOCAL_MODEL_COST_MAP=True` is set before import | same | same | same |
| 18 One request per attempt | achievable only with retries, fallbacks and SDK retries all disabled and proven | same | same | same |

**Other costs:**
- **Supply chain:** LiteLLM 1.82.7/1.82.8 were compromised on PyPI in March 2026 with credential-stealing code. This process holds four provider keys.
- **Dependencies:** a large transitive tree (OpenAI SDK, httpx, pydantic, tokenizers/tiktoken, and more) would all need pinning with hashes under D057.

**Verdict:** end state **C**. Adopting LiteLLM would fabricate zero usage, add import-time network access, and change the endpoints (and therefore the request profiles) of the Google and xAI targets and OpenAI's Responses path. Stopping that would take several escape hatches per provider, which is more code than the roughly 1,360 non-blank lines of adapters it would replace. No smaller multi-provider library was found that keeps the Interactions/Responses endpoints and raw usage facts.

## 4. Chosen provider-layer architecture

```text
canonical workload (workloads)          request profile (targets)
                 \                        /
             benchmark.run_attempt (checks, price, save)
                         |
             latency.measure_request (timing, contract checks)
                         |
             LLMProvider.stream(prompt, cap)
                         |
   openai / anthropic / google / xai adapter   <- provider contract: body from profile,
                         |                         events, usage fields, ids, error codes
             http_streaming                     <- shared: open once, status_failure,
                         |                         checked_usage, StreamContext, sse_events
                   urllib (stdlib)
```

## 5. Retry, fallback and routing behavior after cleanup

- `http_streaming.open_stream` calls the opener exactly once.
- No code path retries, falls back, reroutes, or substitutes a model.
- `run_attempt` refuses a provider whose model differs from its registered profile.
- Tests (`OneRequestPerAttemptTest` and `RealBenchmarkCommandTest`) prove that, for all four adapters:
  - every failure kind (429, 503, timeout, connection refused) and an incomplete stream produce exactly one request;
  - the request body carries the profile's own model;
  - the pilot command makes exactly one request to the chosen provider.

## 6. Modules removed, added, merged

- **Added:** `tests/fakes.py` (test helpers only). No package module was added or removed (25 before, 25 after).
- **Merged:** `real_smoke`'s paid-attempt path into `real_benchmark.run`; `read_failures` into `StreamContext.reading`.

## 7. Before/after LOC

The script `loc.sh` counts physical lines with `wc -l` and non-blank lines with `grep -cv '^[[:space:]]*$'`. "Provider layer" means `providers.py`, `http_streaming.py` and the four adapters.

| Scope | Before (lines / non-blank) | After | Change |
|---|---:|---:|---:|
| Package `llm_metrics/*.py` | 5,737 / 4,960 | 5,590 / 4,810 | −147 / −150 |
| Provider layer | 1,672 / 1,447 | 1,594 / 1,361 | −78 / −86 |
| Paid commands (`real_smoke` + `real_benchmark`) | 299 / 261 | 236 / 203 | −63 / −58 |
| Storage (`storage.py`) | 621 / 565 | 621 / 565 | 0 |
| Tests `tests/*.py` | 7,931 / 7,102 | 8,037 / 7,207 | +106 / +105 |

The test increase is new coverage plus the shared fakes module:
- new tests: about 117 lines (`OneRequestPerAttemptTest`, `SharedHelpersTest`);
- `tests/fakes.py`: 63 lines;
- removed: about 110 lines of duplicated fakes across three test files.

Per-module after: `http_streaming` 318 (+108), `openai_provider` 302 (−60), `anthropic_provider` 266 (−33), `google_provider` 269 (−43), `xai_provider` 219 (−50), `real_smoke` 42 (−79).

## 8. Runtime dependencies

7 before (Flask, Werkzeug, Jinja2, itsdangerous, click, blinker, MarkupSafe) and 7 after, unchanged. No provider SDK, LiteLLM, SQLAlchemy or Alembic was added.

## 9. Meaningful duplicate patterns removed

1. HTTP status mapping (×4).
2. Stream identification/failure closure and enrichment block (×4).
3. Read-error mapping wrapper (×4, now in `StreamContext`).
4. Usage count/cached validation (×4).
5. Paid-command flow (×2).
6. Obsolete OpenAI model override and smoke `MODEL`.
7. Redundant cache-policy validation.
8. Fake HTTP plumbing in tests (×3).

## 10. Intentional duplication retained

- **Per-provider event dispatch, usage field extraction, request-id source, error-code tables and request bodies.** These are the provider contracts. A shared "generic event schema" would hide exactly the differences the benchmark must document (D062–D064).
- **OpenAI vs xAI Responses parsing.** Similar today, but different account errors (OpenAI's in-stream `insufficient_quota`), id source (header vs body) and documented fields. Coupling them would make one provider's change silently alter the other.
- **The OpenAI-specific test file.** It is the live-validated baseline with detailed diagnostics coverage.
- **Hand-written CLI parsing,** to avoid echoing arguments.

## 11. Database/storage reuse assessment

| Question | Assessment |
|---|---|
| Core vs ORM | **Core.** Our rows are facts with nullable semantics and CHECK constraints. Table metadata plus explicit statements keep both visible; an ORM would add identity maps and lazy loading we do not need. |
| Portability SQLite → managed DB | Core metadata can emit SQLite DDL for tests and PostgreSQL DDL for Cloud SQL. Today's text timestamps and `PRAGMA user_version` are SQLite-specific. |
| Transactions | `engine.begin()` gives the same all-or-nothing `save_request`. The IMMEDIATE-lock upgrade becomes Alembic's migration transaction. |
| Unknown-vs-zero constraints | Expressible as `CheckConstraint`s, identical to today's (success ⇒ tokens and costs known; failure ⇒ NULL). Must be kept verbatim and tested on both backends. |
| Migration safety | Alembic revisions replace hand-written steps. The current v0–v7 chain stays for local SQLite only; Alembic's base revision is the v7 schema. |
| Code reduction vs cost | Little reduction now. Value appears with a second database: portable DDL, migrations, connection pooling. Cost: about 3 more dependencies (SQLAlchemy, Alembic, Mako) plus a driver, and every storage test touched. |

## 12. SQLAlchemy/Alembic recommendation

**Recommended for the next persistence step** (the Google Cloud persistence phase), not adopted now:
- adopt SQLAlchemy Core plus Alembic before production data exists;
- start Alembic at the v7 schema;
- keep the constant-SQL style through Core statements;
- run the storage tests against both SQLite and the production engine.

Not now: it is a broad rewrite with no second database to justify it, which is the wrong risk for a behavior-preserving cleanup (D066).

## 13. Tests added, removed, consolidated

- **Added (5 methods in `tests/test_real_providers.py`):**
  - `OneRequestPerAttemptTest`: every failure is one request to the profile's model; an incomplete stream is not retried.
  - `SharedHelpersTest`: status mapping, `checked_usage` unknown-vs-zero and malformed counts, `StreamContext` identification and read-error mapping.
- **Consolidated:** fakes and `no_network` moved to `tests/fakes.py`, now used by `test_openai_provider`, `test_real_providers` and `test_targets`.
- **Adjusted:**
  - the smoke announcement assertion now checks the shared multi-line announcement (same facts: provider, model, profile, workload, cap);
  - the smoke test's adapter patch drops the removed `model` argument.
- **Removed:** none. No test was weakened; the cache-policy refusal test still passes through the profile check.
- **Coverage map for the required list:** items 1–14 and 19 are the existing per-adapter tests; 15–18 are the new no-retry tests plus the pilot-command test; 20 is `ProfileEnforcementTest` plus the storage tests.

## 14. Final test count

**347 tests, OK** (`.venv/bin/python -m unittest discover -s tests`). There were 342 before.

## 15. Formatter and linter

`pyink --check`, `isort --profile google --check-only`, and `pylint --rcfile=.pylintrc --disable=inconsistent-quotes` on `llm_metrics tests scripts`: no findings.

## 16. `./run.sh`

`env -u OPENAI_API_KEY -u ANTHROPIC_API_KEY -u GEMINI_API_KEY -u XAI_API_KEY LLM_METRICS_PORT=0 timeout 120 ./run.sh`:
- ran offline and the tests passed;
- one simulated attempt: workload `interactive-chat-v1`, profile `dummy.dummy-model-v1.v1`;
- served the dashboard until the timeout.

The 14 HTML and API responses rendered with the clock pinned are byte-identical to Step 016.

## 17. Paid and network calls

**None.**
- All provider tests use `FakeOpener`.
- Offline-sensitive tests block sockets and `urlopen`.
- A fresh-process test imports every provider module with sockets disabled.
- The only network use during the step was reading LiteLLM and provider documentation and source.

## 18. Workload hashes

Unchanged. `llm_metrics/workloads.py` has no diff, and the Step 015 SHA-256 golden tests pass, including `interactive-chat-v1`.

## 19. Request profiles

Unchanged. `llm_metrics/targets.py` has no diff, all four profile ids and settings are pinned by `tests/test_targets.py`, and the exact request-body tests for all four adapters pass unchanged.

## 20. Known limitations and remaining cleanup candidates

- **Adapter maintenance:** the four adapters (about 1,360 non-blank lines with the shared module) remain ours to maintain against provider API changes.
- **LiteLLM evidence:** a few cells in the table (SDK retry overrides, request-id access) are unverified. The decision rests on the verified blockers: zero-filled usage, import-time fetch, endpoint changes, and the supply-chain incident.
- **Remaining candidates:**
  - the never-taken "price not yet verified" warning branch (kept as a safety net for future prices);
  - the local SQLite upgrade chain v0–v7 (retire after the Alembic move);
  - the per-provider error-code substring tables, which could become exact-code tables once live errors are observed in 016a.
- **Smoke output:** the `real_smoke` pre-request announcement changed format (now shared with `real_benchmark`); the facts shown are the same or more.
