# Step 024 output — Offline, read-only analytics from immutable GCS records

## Status: COMPLETE (offline), awaiting ChatGPT review

This step built an offline pipeline that turns a local mirror of `llm-metrics.attempt.v1` prod records into one validated, reproducible `llm-metrics.analytics.v1` summary. It was tested on committed synthetic fixtures only. **The real Step 023 pilot mirror was not downloaded or analysed.**

Step 023 is still PARTIAL, with its pilot active until 2026-11-07T18:00Z. Its collector, scheduler, credentials, policy, IAM, alerts and SQL guards are untouched.

## Changed files

| File | Change |
|---|---|
| `llm_metrics/record_analytics.py` | **New.** Loader, population filter, slot evidence, summary, canonical encoder, create-only atomic writer, CLI |
| `tests/test_record_analytics.py` | **New.** 31 tests |
| `tests/analytics_fixtures.py` | **New.** Deterministic generator for the synthetic mirror |
| `tests/fixtures/gcs_mirror/**` | **New.** 18 committed synthetic objects: records, claims, a preflight probe and a CSV backup |
| `README.md` | New section "Offline analytics from GCS records (read-only)", with an exact sample command |
| `DECISIONS.md` | D081 |
| `PROJECT_STATUS.md` | Step 024 state, architecture lines, limitations, next step |
| `design-questions/024/*.md`, `design-questions/README.md` | Four role files and the index row |
| `prompts/chatgpt-conversation.md` | Dated append-only note |

No existing module was modified.

## What it does

```bash
python -m llm_metrics.record_analytics --input MIRROR --output FILE \
  --provider openai --model gpt-6-luna --profile openai.gpt-6-luna.v1 \
  --workload interactive-chat-v1 --origin gcp/us-central1 \
  --start 2026-11-06T18:00:00Z --end 2026-11-07T18:07:00Z \
  [--prefix attempts] [--collector-policy-start 2026-11-06T18:00:00Z]
```

`MIRROR` is the bucket contents, for example from `gcloud storage cp -r gs://BUCKET/attempts/v1 MIRROR/attempts/`. Running that copy is an operator action and was **not** done here. Every argument except `--prefix` and `--collector-policy-start` is required. Nothing defaults to live GCS.

**Reading and validation:**
- Only `MIRROR/<prefix>/v1/requests/prod/<day>/` is read, for the days that overlap `[start, end)`.
- Every file in those days is validated by `object_results.decode_record(data, expected_name=…)`, including files the filter then excludes. That one call covers UTF-8 JSON, duplicate keys, NaN, canonical bytes, schema v1 with outcome consistency, and the object name, so the schema is not re-implemented here.
- A `test` record copied into `prod/`, or a record placed under the wrong date or id, fails.

**Selection:**
- Records are matched by exact provider, model, profile, workload, origin cloud and region, and time.
- Excluded records are counted by reason: `outside_time_window`, `other_profile`, `other_workload`, `other_origin`.
- A record with the selected profile but another provider/model fails the run (mixed population).
- `test` records and `snapshots/` CSVs are never read. `source.csv_backups_included` is `false`.

**Fail-closed** (exit 1, nothing written) for:
- a missing input, an unsafe prefix, or a symlink anywhere under the prefix
- more than 200,000 entries, unexpected directory entries, non-record file names, or files over 64 KiB
- invalid, non-canonical, corrupted or misplaced records
- duplicate provider request ids, which are never echoed
- mixed populations, inconsistent slot evidence, or zero matching records

Bad arguments exit 2.

**Summary (`llm-metrics.analytics.v1`):**
- **Identification:** `population` (the exact filter); `source` (files scanned, exclusions); `data_window` (earliest and latest `recorded_at`).
- **Reliability:** `outcomes.success_rate` over **all** selected attempts, with failures by category.
- **Metrics:** for each `latency.METRICS` entry, over successes only: unit, count, `successes_without_value`, nearest-rank p50/p95 (`percentiles.percentile`), min, max, and latest (value, time, attempt id). With no values they are `null`, never 0.
- **Costs and tokens:** `cost_usd` gives known total, input and output cost over successes (`math.fsum`), `priced_successes` and `failed_attempts_cost_unknown`. `tokens` gives input and output totals plus known cached tokens and the count of successes whose cached tokens are unknown.
- **Settings:** `request_settings` (cache policies, output caps, distinct prices) and `provenance` (records without a provider request id).
- **Slot completeness and caveats:** `slot_completeness` (see below), and `caveats` as machine-readable codes: `observed_success_rate`, `no_slot_evidence` or `slots_without_records`, `partial_day`, `small_sample` (fewer than 100 successes), `p95_is_sample_max` (fewer than 20), `failed_cost_unknown`, `throughput_undefined_for_some`.
- **Evidence:** per record, the object name, attempt id, recorded_at, outcome and SHA-256 of the exact bytes, plus `manifest_sha256`. The manifest hashed is the `sha256sum`-format text (`<sha>  <object name>\n` per record), so `sha256sum -c` from the mirror root can verify it.
- **Never written:** provider request ids, prompts, responses, keys or wall-clock "generated at" fields.

**Slot completeness** is reported only with `--collector-policy-start`.
- It calls `collector_audit.audit` over the claims in the same mirror, with `now = end − 1 µs`. Slot state is not re-implemented.
- The run requires:
  - the collector's fixed scope;
  - `--start` equal to the policy start;
  - `--end` no later than the expiry plus the late limit;
  - no selected record listed as `records_without_claim`;
  - the audit's recorded success/failure counts equal to the selection's;
  - every recorded-failure id selected.
- Without the flag, `slot_completeness` is `null`. Missing slots are never added to attempts or to the reliability denominator.

**Write:** the canonical bytes (sorted keys, compact, `allow_nan=False`) are written to a temp file in the destination directory, fsynced, then `os.link`-ed into place, which is atomic and create-only, and then the directory is fsynced.
- An identical existing file gives "Unchanged" (exit 0).
- A different existing file, a symlink, a missing directory, or a path inside the mirror is refused.

## Decisions

**D081** (`DECISIONS.md`):
- Published analytics come from this offline summary over immutable records, not from the SQL dashboard.
- Slot completeness only comes from claims evidence.
- The schema is the contract for future static pages (D069).

**Implementation choices:**
- **`os.link` instead of `os.replace` for the final step.** It is still temp + atomic rename semantics, but it cannot overwrite, which matches the immutable-evidence model.
- **No wall-clock `as_of` field.** The population's `end_exclusive` is the cut-off, which keeps output byte-identical.
- **`argparse`** (standard library) instead of the hand-rolled parser in `collector_audit`.
- **No new dependencies.**

## Evidence and tests

**Synthetic fixture.** The policy is 2026-01-05T18:00Z, chosen to predate all real data. Sequential attempt ids and `synthetic-req-NNNN` request ids make it clearly synthetic.
- **Window 18:00–20:00Z:** 5 successes, 1 `provider_error`, 1 missing slot, 1 claim without a record.
- **Exclusion cases:** a one-off record at 17:10Z, another workload at 18:20Z, a `test` record, a preflight probe, and a CSV backup.

**Result on the fixture:**
- attempts 6 (5 success, 1 failure); 8 begun slots (5 / 1 / 1 claim without record / 1 missing)
- TTFT p50 1650.25 ms, p95 = max 2210.75 ms
- tokens/s count 4, with 1 success without a value
- known cost $0.0003045, with 1 cost unknown
- a second run is byte-identical

**`tests/test_record_analytics.py`, 31 tests:**
- **Fixtures:** the committed files equal the generator's output, and the request ids are synthetic.
- **Full CLI with slot evidence,** under `fakes.no_network` with `GcsObjectStore` patched to fail if constructed: the counts, percentiles, costs, tokens, exclusions, caveats, canonical bytes, and absence of request ids, test records and CSVs listed above.
- **Repeatability:** byte-identical repeat runs, and the "Unchanged" path.
- **Evidence:** the manifest matches the file hashes.
- **Populations:**
  - records-only mode gives `null` slots;
  - the one-off population stays separate;
  - a failures-only window gives nulls, not zeros;
  - non-finite values are refused.
- **Input refusals:**
  - zero rows, another region, a missing input
  - malformed JSON, non-canonical, invalid-schema, misplaced and corrupted records
  - a test record in the prod directory, an oversized file, unexpected entries
  - a symlinked file or directory, an unsafe prefix
  - duplicate provider request ids, a mixed provider/model under one profile
  - an unclaimed record with slot evidence, a window that cuts off a slot's record, and scope/start/alignment checks
- **Output refusals:** a different existing file is kept; output inside the mirror, a symlink, or a missing directory is refused.
- **Argument errors** exit 2.

**Validation run:**
- Focused: `.venv/bin/python -m unittest tests.test_record_analytics` → 31 tests OK.
- **Full Docker `./run.sh test` (Compose, PostgreSQL 17): `Ran 564 tests`, `OK (skipped=5)`, 0 failures.**
  - The count was 533 before this step, plus 31.
  - The 24 PostgreSQL integration tests ran and passed.
  - The 5 skips are the pre-existing container-config tests, which skip outside the repository root inside the container.
  - The dashboard smoke test returned HTTP 200.
- Style, run in a `python:3.13-slim` container:
  - `pyink --check`, `isort --profile google --check-only` and `pylint --rcfile=.pylintrc --disable=inconsistent-quotes` are **clean on all three new Python files**.
  - Repository-wide, pyink would reformat 12 existing files and isort flags 4 existing files. Neither tool flags any file changed in this step, and those findings were left alone as out of scope.

## Limitations

- **Synthetic only:** it has not been run on the real Step 023 mirror, and real-layout compatibility rests on the shared `object_results` and `collector_audit` code paths.
- **Partial validation:** only day directories that overlap the window are decoded. Corrupt files on other days are not detected by that run.
- **Slot evidence scope:** it is tied to the Step 023 collector's fixed scope and one 24-hour policy. Agreement is checked by counts plus failure ids, because `audit` doesn't expose the ids of claimed successes.
- **Statistics:** there are no confidence intervals. With fewer than 20 successes p95 is the maximum, and with fewer than 100 it is unstable. These are flagged as caveats.
- **Filesystem and links:** `os.link` needs hard-link support. Hard links inside the mirror are not detected; the hashed bytes are still the evidence.
- **Two analytics paths:** the SQL dashboard and this summary are not reconciled.

## Expense and cloud actions

**None.** There were no provider calls, no GCP reads or writes (the bucket was not listed or copied), no deployments and no IAM changes. Docker was used locally for tests and lint only.

## Commit

The commit is the one that adds this file. Its SHA is reported in the hand-off message.

## Recommended next step (one)

After ChatGPT review:
1. Close Step 023 when its window ends: run the post-window audit and the stop.
2. Then, with explicit approval, make a read-only local mirror of `attempts/v1` and run `record_analytics` over the full window with `--collector-policy-start 2026-11-06T18:00:00Z`, producing and reviewing the first real `llm-metrics.analytics.v1` summary before Step 025 consumes it.

## MARKETING CHECKPOINT

- **Educational claims we can make now:**
  - llm-metrics computes its published statistics from immutable, per-attempt, hash-listed records.
  - Failures stay in reliability denominators and never become zero latencies.
  - Missing scheduled slots are reported separately from provider failures.
  - Summaries are byte-reproducible from the same evidence.
- **Not publishable yet:**
  - any OpenAI performance number, success rate or cost from the pilot: the summary has not been generated from real data, the window is still open, and it is one provider, one model, one origin and at most one day;
  - any ranking or comparison between providers (only one is measured);
  - any claim of provider uptime.

## Design Q&A (concise)

- **Lead engineer:** *How does a damaged mirror fail to produce a plausible summary?* Every scanned file goes through `decode_record` with its expected name. Symlinks, unexpected entries, oversized files, duplicates, mixed populations and zero rows all refuse before any write. Output is canonical, without wall-clock fields, and create-only. *Weakness:* only overlapping days are validated.
- **Principal engineer:** *Why delegate slot completeness to `collector_audit` over claims, and how are slots and records kept consistent?* Records cannot encode slots that never ran. The run requires scope, start, no unclaimed selected record, and equal success/failure counts and failure ids. *Weakness:* coupled to the fixed 24-hour scope; no full id-set check.
- **Senior manager:** *What can be said from this summary?* The observed success rate, success-only percentiles, and known spend with unknown costs counted, for one exact population. It cannot support uptime, precise p95 at small n, rankings, or "every slot succeeded" without claims. Caveats are embedded in the file.
- **Director:** *A file-based offline summary instead of BigQuery or the SQL path?* Yes at this scale: no new paid resource, the strongest provenance, and it matches D069 static publishing. Revisit at multi-provider, multi-month volume (Parquet or BigQuery over the same immutable objects). *Weakness:* the two analytics paths are unreconciled, and the mirror step is manual.

Full role files: `design-questions/024/`.

**STOP: awaiting ChatGPT review. Step 025 not started.**
