# Lead engineer — Step 028: production thresholds and metric snapshots

**Step context:** Step 028 (first part) added production publication thresholds (`static_site.production_gate`: complete 24-hour window, evidence for every slot, at least 50 successes, at most 5% unrecorded slots) and dated immutable metric snapshots (`/reports/YYYY-MM-DD/openai-ttft-measurements`, archived in the publication manifest under `metric_snapshots`). The complete OpenAI pilot (96 slots, 95 successes) passed and was published on llmxchange.com with its charts. The weekly cloud publisher and weekly cost editions are not built yet.

---

## Question

How is a metric snapshot made immutable and idempotent, and how does it coexist with the question editions in one archive?

## Answer

- With `--publish-at` and a gated real dataset whose SHA-256 is not yet in `metric_snapshots`, `_plan_snapshots` renders the metric page at `/reports/<date>/openai-ttft-measurements` (`/rN` for a second snapshot on the same day) and `build` freezes it create-only with its `html_sha256`, dataset hash, record manifest hash, window, methodology version and site URL.
- Later builds serve the archived bytes verbatim and refuse a modified file or a different site URL. Re-running with the same dataset creates nothing (tested; the real publish created one snapshot).
- `plan_editions` counts snapshot routes as expected archive files, so the stray-file check still guards the whole archive. Staging builds ignore the archive.

## Critique

Snapshots key on the dataset hash, so a recomputed summary with identical numbers but a different window would create a new snapshot; that is intended but should be documented for weekly runs.

---

## Question (part 2: weekly publisher)

How does the weekly run stay idempotent when Cloud Scheduler retries or the job crashes mid-run?

## Answer

- Each scheduled week (latest Sunday 02:00 UTC at or before `--now`) is recorded in `state.json`; a retry returns `already_done` without building.
- Archive writes are keyed by content, not time: a dataset already in `metric_snapshots`, a cost `content_sha256` already in `cost_editions`, or an already archived edition creates nothing. A crash after freezing but before recording therefore re-runs harmlessly.
- `build` now checks the output path before freezing, so a refused output can no longer leave new archive entries behind.

## Critique

The state file is a single JSON file; in the cloud it must be uploaded with a generation precondition, or two overlapping executions could both run. Cloud Run Job parallelism 1 and scheduler retries 0 make that unlikely, not impossible.
