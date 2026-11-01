# Step 015 — Implementation report

Prompt: `015-versioned-benchmark-workloads.md`.

## Files / modules changed

- **`llm_metrics/workloads.py` (new, 651 lines, standard library only):** the workload catalogue.
  - `Workload` (frozen dataclass), validated when built.
  - `CATEGORIES`, the six benchmark definitions, `SMOKE_SHORT_TEXT_V2`, `BENCHMARK_WORKLOADS`, `DEFAULT_WORKLOAD_ID`, `list_workloads()`, `get_workload()`, `UnknownWorkloadError`.
  - The deterministic content builders (`_interactive_chat_prompt`, `_coding_prompt`, …).
- **`llm_metrics/benchmark.py`:** `run_attempt(provider, workload, environment, db_path, *, origin)` replaces `run_attempt(provider, prompt, max_output_tokens, environment, db_path, *, workload_id, origin)`. It refuses non-canonical workloads before doing anything.
- **`llm_metrics/__main__.py`:** `main(argv=None)` with `--workload WORKLOAD_ID` (default `interactive-chat-v1`). The old `WORKLOAD_ID`/`PROMPT`/`MAX_OUTPUT_TOKENS` constants are removed.
- **`llm_metrics/real_smoke.py`:** `WORKLOAD = workloads.SMOKE_SHORT_TEXT_V2` replaces the three constants. The announcement now names the workload. The request is otherwise unchanged.
- **Tests:**
  - New `tests/test_workloads.py` (19 tests).
  - `tests/test_cli.py`:
    - Expectations updated for the new default.
    - New tests: every workload runs and is stored with its id, cap and simulated input count; unknown ids and bad arguments are refused.
  - `tests/test_openai_provider.py` migrated to the new `run_attempt` signature. The secret-handling test now checks that the smoke prompt is never printed or stored.
  - `tests/test_web.py`: `workloads` added to the layering test and the "loads without Flask" list.
  - `tests/test_run_script.py`: expects `Workload: interactive-chat-v1`.
- **Docs:**
  - `DECISIONS.md`: D061 added; D050 annotated.
  - `PROJECT_STATUS.md`.
  - `README.md`: new "Benchmark workloads" section, plus updated request facts, sample output and manual commands.
  - `llm_metrics/README.md`.
  - `prompts/chatgpt-conversation.md`.
  - `design-questions/15/` and its index row.

## Workload representation and catalogue

```python
@dataclasses.dataclass(frozen=True)
class Workload:
    workload_id: str          # stable, versioned, stored with every attempt
    category: str             # one of CATEGORIES
    version: int              # the id's suffix
    name: str
    description: str
    prompt: str               # the complete input; never stored or printed
    max_output_tokens: int    # the cap requested from the provider
    target_input_tokens: int  # approximate design size, not a provider count
```

`__post_init__` rejects a definition if any of these hold:
- the id is not versioned (lowercase words ending in `-vN` or `.vN`) or doesn't end in its `version`;
- the category is unknown;
- the name, description or prompt is blank;
- a size is not positive.

The six benchmark ids are also tested to have the canonical form `<category with dashes>-v<version>`. So the identity is written out explicitly and checked; callers never concatenate it.

| Workload id | Category | Output cap | Target input | Content |
|---|---|---:|---:|---|
| `interactive-chat-v1` | interactive_chat | 300 | ~2K | Support assistant for a fictional notes app: product facts, 24 sync-setting entries, a 6-turn conversation, and a question needing a step-by-step explanation |
| `coding-v1` | coding | 1000 | ~8K | 41 small Python depot-rule modules (correct, context), a buggy `allocate_stock` (takes reserved units), its failing test; asks for diagnosis, fix, edge cases, two tests |
| `rag-v1` | rag | 500 | ~16K | 145 transit-route documents; a question combining Route 14 and Route 47 with citations and an estimate |
| `summarization-v1` | summarization | 1000 | ~32K | Three years × 6 departments = 216 sections of committee minutes; a structured summary under fixed headings |
| `extraction-v1` | extraction | 150 | ~4K | 55 shipment notices to classify (`on_time` / `damage_reported` / `paperwork_missing`) into a small JSON object of counts and flagged ids |
| `agent-tool-v1` | agent_tool | 300 | ~8K | 66 tool descriptions, a 12-step log of earlier read-only calls (all naming listed tools), a goal; asks for the next tool call and arguments as text |
| `smoke.short_text.v2` | smoke | 64 | ~15 | The existing real-provider connectivity check (unchanged text); not a benchmark workload |

- **The extraction cap:** a 150-token cap is too small for one JSON object per notice, so the task asks for counts plus flagged ids. That keeps the output shape predictable within the cap.
- **The smoke workload's id:** it keeps its pre-catalogue id, `smoke.short_text.v2`. The only real attempt (`44c889cb…`) was recorded under that id with exactly this content, and renaming identical content would wrongly split one population.

## How the deterministic content is built and stored

The content lives in code, as small builder functions in `workloads.py`. It is not in fixture files.

- **Hand-written parts:**
  - each workload's instructions and question;
  - the bug and its test in `coding-v1`;
  - the conversation in `interactive-chat-v1`.
- **Generated parts:** the repeated material (settings, modules, documents, sections, notices, tools) comes from one f-string template per workload.
  - Values are filled from fixed invented-name lists via `_pick(values, index, step)` and integer formulas such as `6 + (i * 5) % 19`.
  - The formulas keep facts coherent: completed tasks never exceed planned ones, resolved requests never exceed filed ones, and logged tool calls only name listed tools.
- **Never used:** randomness, dates, environment variables, files or network.
- **Building:** the catalogue is built once at import, which takes about a millisecond.

Why generated code instead of ~280 KB of committed text:
- It keeps the repository small (651 lines in total).
- A reviewer can read each workload's structure in one template, not thousands of lines.
- All of it is original and fictional, so it is safe to publish.

Trade-off: the material is repetitive. Real application text is less regular, and repetition may tokenize, cache or compress differently from natural text (see limitations).

**Tests that protect it:**
- A pinned SHA-256 per prompt; the failure message says to add a new version instead.
- A rebuild in a fresh interpreter with `PYTHONHASHSEED=12345`, which must produce identical hashes.
- A size check (0.9–1.1 of the target at 4 characters per token).
- No dates, URLs, key-like strings, or non-ASCII characters in any prompt.
- The six prompts are distinct and differ in size by more than 10×.

## Approximate input sizes achieved

Measured with non-provider methods only: characters, whitespace-separated words, and `ceil(characters / 4)`. That last figure is also what the dummy provider's simulated tokenizer reports. **None of these are provider token counts.** Code-heavy and number-heavy text (`coding-v1`, `rag-v1`) usually tokenizes denser than 4 characters per token, so real counts will likely be higher there.

| Workload | Target tokens | Characters | Words | chars ÷ 4 | ÷ target |
|---|---:|---:|---:|---:|---:|
| `interactive-chat-v1` | 2,000 | 7,816 | 1,313 | 1,954 | 0.98 |
| `coding-v1` | 8,000 | 32,160 | 3,597 | 8,040 | 1.00 |
| `rag-v1` | 16,000 | 64,189 | 11,164 | 16,048 | 1.00 |
| `summarization-v1` | 32,000 | 123,764 | 20,619 | 30,941 | 0.97 |
| `extraction-v1` | 4,000 | 16,224 | 2,501 | 4,056 | 1.01 |
| `agent-tool-v1` | 8,000 | 31,507 | 4,063 | 7,877 | 0.98 |
| `smoke.short_text.v2` | 15 | 65 | 10 | 17 | 1.13 |

## Benchmark and CLI integration

```text
workloads.get_workload(id) -> benchmark.run_attempt(provider, workload, ...) -> latency.measure_request(provider, workload.prompt, workload.max_output_tokens) -> storage.save_request(... workload_id=workload.workload_id ...)
```

- **`run_attempt`** first checks `get_workload(workload.workload_id) == workload`. An unknown id (`UnknownWorkloadError`) or an edited copy (`ValueError`) is refused before pricing, the provider call, or any database write.
- **One provider call per attempt:** a short answer is stored as is, and failures are not retried. The existing `latency` checks (output must not exceed the cap, usage must be reported once) are unchanged.
- **`python -m llm_metrics [--workload ID]`** parses its arguments before reading `APP_ENV`, the provider or the origin.
  - An unknown id, missing value or extra argument exits 2 with nothing measured or saved.
  - The error lists the valid ids (`Unknown workload. Valid workloads: interactive-chat-v1, …`) or prints the usage line, and never echoes the input.
- **`./run.sh`** runs the default `interactive-chat-v1` with the dummy provider. It is just as fast as before, because the dummy ignores content apart from counting it. Its output now reads `Input tokens: 1954 (simulated)`, `Output tokens: 7 of max 300`, cost $0.003964 (simulated).
- **`real_smoke`** is unchanged in behavior: same prompt, cap and request, and still exactly one explicit paid call that requires `OPENAI_API_KEY`. Its announcement now includes `workload smoke.short_text.v2`.
  - It deliberately does **not** accept `--workload`. Sending the large workloads to a paid provider is Step 016/017 work with its own cost controls.

## Dependency direction

```text
workloads (definitions; imports only dataclasses, re)
    ↓
benchmark (runs one workload once) → latency / providers (timing, protocol) → storage (facts)
```

- `workloads` imports nothing from `llm_metrics`, which is enforced twice:
  - `test_workloads`: its imports are exactly `{dataclasses, re}`;
  - the `test_web` layering test bans `analytics`, `benchmark`, `latency`, `openai_provider`, `providers`, `query`, `storage`, `dashboard`, `api` and `web`.
- It loads without Flask, Werkzeug, Jinja or MarkupSafe (fresh-process test).
- Providers never import workloads: an adapter still receives only `(prompt, max_output_tokens)` through `LLMProvider.stream`.

## Versioning and fairness semantics

- **Workload id is measurement identity**, beside provider/model, origin, cache policy and time.
- **Released versions are frozen.** Anything that would make results not directly comparable (content, instructions, task, or cap) becomes `<id>-v<N+1>` beside the old one. The pinned hashes make an accidental in-place edit fail CI, and retired ids stay valid in stored data. There is no migration or deprecation machinery.
- **Fairness = same content and semantics, not same token counts.** Every provider gets identical text for a workload version. Their reported `input_tokens` will differ (tokenizers, request wrappers), and those differences are stored as facts. No provider tokenizer was added, and `target_input_tokens` is only a design label.
- **The cap is a cap.** `requested_max_output_tokens` and `output_tokens` stay separate facts. There is no minimum length, retry or extension.
  - A test makes the provider report `output_tokens = 3` under `rag-v1`'s cap of 500. It stores 3 and 500 and makes exactly one call.
  - Another test reports `input_tokens = 15,101` against `rag-v1`'s 16,000 target, and 15,101 is what gets stored.

## Tests and style

- **283 tests, OK** (264 before; 19 new in `test_workloads.py` and 2 new in `test_cli.py`), under the project venv (Python 3.13). None skipped.
- **Prompt checklist:**
  1–6. The catalogue and the canonical lookup (items 1–6) are covered.
  7. Unknown ids fail clearly, both from `get_workload` and from the CLI, before measuring.
  8–9. Orchestration sends the canonical prompt and cap once and stores the id, for every workload.
  10–12. Provider token facts stay separate from size targets and from the cap; nothing is retried.
  13. Dependency independence is checked.
  14. `real_smoke` is still fixed to the small smoke workload, and all existing real-call safety tests pass.
  15. Every test blocks or fakes the network.
  16. `./run.sh` passes, both run manually and in the end-to-end test.
  17. API and dashboard compatibility: 14 responses rendered by the 014d commit and by this change, against the same database copy with a fixed clock, are **byte-identical**:
     - 11 HTML responses;
     - 3 `/api/v1/metrics` responses.
  18. Style is clean (below).
- **Style:** pyink, isort (google) and Google pylint report no findings. The style fixes moved string literals only; the content hashes did not change.
- **`./run.sh`:** "Dependencies ready" and "Tests passed", then `Workload: interactive-chat-v1` saved. The dashboard served `/`, `/requests`, `/spend` and `/api/v1/metrics` with 200, and `/requests` shows the new id.

## Paid or network calls

None. No real provider was called. The only network-capable path (`real_smoke`) was exercised only through existing tests with a fake opener.

## Known limitations

- **Hypotheses:** the six workloads are not validated by user research, and their names and sizes are design choices.
- **Estimated sizes:** input sizes come from a 4-characters-per-token estimate. Real provider counts will differ, and probably be higher for code and number-dense text.
- **Repetitive content:** the templated material may let some models answer faster, or let caches or compression behave differently than on natural text. That is a known bias of synthetic workloads.
- **No quality checks:** answers are not evaluated. A provider that refuses or answers off-task still records valid performance numbers.
- **`agent-tool-v1` is plain text:** it asks for a tool choice in text, with no native tool calling. Its latency is not a measure of provider tool-calling overhead.
- **Request shape outside the id:** provider settings such as OpenAI `reasoning.effort` and the cache control are adapter-level and not part of the workload id, except that the legacy smoke id stands for its request shape. Step 016 must decide how adapter request profiles enter the measurement population.
- **No workload filters yet:** the aggregate page and `/api/v1/metrics` don't filter by workload, so simulated runs of different workloads share one population there. The simulated provider's timings don't depend on content anyway.
- **History split:** `./run.sh` now records `interactive-chat-v1`, so simulated history spans `simulated.default.v1` (older rows) and the new id.
- **Not runnable on a real provider yet:** `real_smoke` cannot run benchmark workloads, and there is no cost guard for the large ones yet.

## What Step 016 can rely on

- A provider adapter implements only `LLMProvider.stream(prompt, max_output_tokens)` and reports `Usage`. It never defines or alters workload content.
- `workloads.get_workload(id)` returns frozen, deterministic content. `benchmark.run_attempt(provider, workload, ...)` sends it unchanged, stores the canonical id, and records the provider's own token counts.
- Adding or re-versioning a workload needs no change to providers, storage, analytics or the web layer.
- Unknown or edited workloads are refused before any paid call.

## Marketing checkpoint inputs

- **Milestone:** a versioned, deterministic benchmark workload catalogue integrated into the benchmark runner (Step 015).
- **Catalogue:**

  | Workload | Output cap | Approx. input (chars ÷ 4) |
  |---|---:|---:|
  | `interactive-chat-v1` | 300 | 1,954 |
  | `coding-v1` | 1000 | 8,040 |
  | `rag-v1` | 500 | 16,048 |
  | `summarization-v1` | 1000 | 30,941 |
  | `extraction-v1` | 150 | 4,056 |
  | `agent-tool-v1` | 300 | 7,877 |

  The approximate input sizes are not provider-measured. There is also a `smoke.short_text.v2` connectivity check.
- **Reproducibility decisions:**
  - Content is original, synthetic and built deterministically in code, with each prompt pinned by SHA-256.
  - Any material change creates a new version.
  - Fairness is defined as identical content, not identical token counts. Each provider's own token counts are recorded as facts.
  - Output caps are maxima, with no retries.
- **Sample facts:** none from real providers. No workload has been sent to any real provider yet, and the only real data remains one successful smoke request (`gpt-6-luna`, 2026-10-30).
- **Tests:** 283 passing; style checks clean; no paid or network calls.
- **Limitations:**
  - The workloads are hypotheses pending user research.
  - No cross-provider or cross-model comparison data exists.
  - Sizes are estimates.
  - Content is synthetic and repetitive.
  - Answer quality is not evaluated.
- **Paths:** `llm_metrics/workloads.py`, `tests/test_workloads.py`, `README.md` ("Benchmark workloads"), `DECISIONS.md` D061, `prompts/015-output.md`. Commit: see the git log entry "Step 015: versioned benchmark workload catalogue".
- **Technical observations:**
  - Equal content does not mean equal tokens: token counts will differ by provider for the same text, so tokens/s is not directly comparable across providers. Per-request latency is the cleaner cross-provider figure. This is a methodology point, not a measured result.
  - The one-JSON-object-per-item extraction shape didn't fit a 150-token cap. The output cap shapes the task design, not just the cost.
