# Step 013 — Implementation report

Prompt: `013-metrics-v1-data-completeness.md`.

**Scope note:** this report covers requirements 1–3 (tokens/s, workload, origin), implemented against the prompt as of `3650f7b`. Requirement 4 (cache policy and cached input tokens) was added to the prompt afterwards (`399d963`) and is **not implemented** here.

## What changed

- **`output_tokens_per_s` (D049).**
  - `measure_request` adds it to a successful attempt as `Usage.output_tokens / (last non-empty chunk time − first non-empty chunk time)`. That's the same timing boundary as `output_chunks_per_s` (Step 009), so TTFT is excluded.
  - It's omitted when there are fewer than 2 non-empty chunks, no elapsed time, or 0 reported output tokens.
  - `METRICS` lists it before chunks/s, labelled "Output token throughput" in tokens/s.
  - `output_chunks_per_s` is unchanged in name, formula and storage. Only its display label is now "Output chunk throughput", so the two aren't confused.
- **`workload_id` (D050).** A required, keyword-only `run_attempt(..., workload_id=...)`. `python -m llm_metrics` uses `simulated.default.v1` and `real_smoke` uses `smoke.short_text.v1`. Both are module constants, with a comment to bump the version when the case changes.
- **Origin (D051).**
  - `config.get_origin()` reads `LLM_METRICS_ORIGIN_CLOUD` / `LLM_METRICS_ORIGIN_REGION`, defaulting to `local` / `unknown` when unset or empty.
  - Values must be lowercase letters, digits and inner hyphens, at most 63 characters.
  - Both entry points read it before any measurement or request; an invalid value exits 2 without echoing it.
  - It's passed as `run_attempt(..., origin=(cloud, region))`.
- **Storage:** `requests` gains `workload_id`, `origin_cloud` and `origin_region`. `save_request` refuses a new attempt without non-empty values for all three, and the request row and observations are still written in one transaction.
- **CLI and `real_smoke` summary:** new `Workload:` and `Origin:` lines; tokens/s is printed before chunks/s.
- **Dashboard:**
  - `/requests` (simulated and real) has Throughput (tokens/s) before Throughput (chunks/s), plus Workload and Origin columns. Unknown values show as "—".
  - The aggregate metric selector now includes token throughput (simulated data only, as before).
- **Docs:** `DECISIONS.md` (D018, D034, D035, D037 revised; D049–D051 added), `PROJECT_STATUS.md`, README, `llm_metrics/README.md`, the project direction log's progress line, and `design-questions/13/` with its index row.

## Migration (schema version 4 → 5)

- One `if version < 5` step runs inside the existing `BEGIN IMMEDIATE` upgrade transaction. It adds the three nullable columns with `ALTER TABLE ADD COLUMN`; there's no rebuild, and existing rows are untouched.
- Historical workload and origin stay **NULL (unknown)**. Workload could have been guessed from the environment (prod means smoke, test means simulated). But the real case wasn't stable: the first real attempt was sent without `reasoning.effort`, and later ones with `none`. So any label would be a guess. Origin was never recorded.
- No observations were backfilled, so the one real success has no tokens/s value.
- On the local database: it moved from version 4 to 5. The 10 earlier requests are all present, with the three new facts NULL; the 11th, the new simulated attempt, has them. Exact preservation of every field and observation is checked by the migration test, not by a before/after comparison of this database.

## Choices made

- **Tokens/s for every provider, not only real ones.** Measurement stays provider-agnostic. The dummy's value is labelled simulated, like its token counts, and it gives the aggregate chart and the run.sh test something to exercise.
- **0 output tokens means no tokens/s.** A zero rate next to visible text would be contradictory data, not a measurement.
- **Exact formula as specified** (`output_tokens / duration`, not `(tokens − first-chunk tokens) / duration`). We can't know how many tokens the first chunk held, so the bias toward high values on short responses is documented instead of corrected.
- **Required facts are enforced in code** (`run_attempt` has no default; `save_request` raises), and the columns are nullable so old rows stay honest. There's no `NOT NULL` with a placeholder default.
- **Origin is validated before any work.** A typo in deployment config fails loudly instead of creating a new "region". There's no allowlist of clouds, because the format check is conservative enough without one.
- **No index on the new columns.** Filtering can use them as plain columns; an index can come with the first query that needs it.

## Tests

182 tests, OK on Python 3.13 (3.11 is not installed here). New or changed tests:

- **Tokens/s:**
  - With a controlled clock: 5 tokens over 0.080 s gives 62.5 tokens/s next to unchanged 50 chunks/s.
  - With 3 chunks but 40 reported tokens, the result is 200 tokens/s. TTFT (1.0 s) and the stream tail are excluded, and chunks/s is still 10.
  - It's omitted for a single chunk, zero elapsed time, and 0 output tokens.
  - The catalogue order and labels are checked.
- **Workload and origin:**
  - The CLI prints and saves both, from the environment.
  - An invalid origin exits 2 before measuring, without echoing it, and creates no database.
  - `real_smoke` stores `smoke.short_text.v1` and the origin, and shows tokens/s from OpenAI's usage.
  - An invalid origin in `real_smoke` exits 2 with zero HTTP calls.
  - `save_request` refuses each missing or empty fact.
  - `get_origin` defaults, explicit values, and 7 invalid forms are covered.
- **Migration:** a version-4 table with a real success row and its observation upgrades with every fact (including `provider_request_id`) preserved, workload and origin NULL, new saves working, and a re-upgrade that changes nothing. The schema version is 5.
- **Views:**
  - The requests table shows tokens/s before chunks/s, plus workload and origin.
  - A failed row still shows its workload and origin.
  - Historical rows show "—".
  - The real view shows tokens/s, workload and origin.
- **Unchanged guarantees:** existing no-network tests (blocked socket and urlopen, the fake opener, and the fresh-process import check) still pass. `run.sh` end-to-end now expects 4 observations per run.

`./run.sh` (APP_ENV unset, `OPENAI_API_KEY` unset): tests passed, history present, and one simulated attempt saved with `Workload: simulated.default.v1`, `Origin: local / unknown`, 85.9 tokens/s and 49.1 chunks/s. The dashboard served until stopped.

**No paid API call** was made by the implementation or tests in this step.

## Known limitations

- Tokens/s is effective, client-observed throughput. It includes first-chunk and reasoning tokens, reads high for very short responses, and isn't internal decoding speed.
- Nothing enforces a `workload_id` version bump when a prompt or cap changes; it's a convention backed by comments.
- Origin isn't verified; it's whatever the runner is configured to report. There are no origin or workload filters or views yet.
- Historical rows have no workload, origin, or tokens/s value.

## Design Q&A

**Why divide all output tokens by the first-to-last chunk interval?** It's the only interval the client can observe that excludes queueing and prefill (TTFT), and the provider's count is the only authoritative token number. Their mismatch (the first chunk's tokens arrive before the interval starts) is small for real responses of more than a few chunks, and it's documented rather than hidden.

**Why are workload and origin columns and not metric rows?** They describe the conditions of a request, not something measured about it. As columns they apply to failed attempts too (which have no observations), and they can filter every metric population with one `WHERE`.
