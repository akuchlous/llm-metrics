# Step 004 — Implementation report

Commit: `e7b9210`. Prompt: `004-simulated-history.md`.

## What was implemented

`python3 -m llm_metrics.seed_history` inserts 168 deterministic hourly simulated TTFT rows (2026-10-23 00:00 to 2026-10-29 23:00 UTC, `test`/`dummy`/`ttft`). Re-running inserts nothing.

## Files

- `llm_metrics/seed_history.py` (new) — `simulated_ttft_history()` (pure, fixed seed) and the `main()` command.
- `llm_metrics/storage.py` — unique index, `format_timestamp()`, `save_new_observations()` (`INSERT OR IGNORE`, returns the number inserted).
- `tests/test_seed_history.py` (new).
- `README.md`, `PROJECT_STATUS.md`, `DECISIONS.md` (D022–D024).

## Tests / run

- 38 tests, OK. `./run.sh` passed from a fresh `.venv`.
- Seed output: `168 new, 0 already present`, then `0 new, 168 already present`.
- On a database created by Step 003, row counts went 3 → 171 (seed) → 171 (re-seed) → 172 (`./run.sh`).
- Values: median ~101 ms, minimum 80 ms, five spikes of 294–476 ms.
- `APP_ENV=prod` exits 2 and writes nothing.

## Design decisions and why

- **Fixed calendar window**, not "the last 7 days". It is fully reproducible, and duplicate checks are trivial.
- **Values centred on 100 ms**, the dummy's delay, so history and live runs look continuous on a graph.
- **Duplicates prevented by a unique index on (`recorded_at`, `environment`, `provider`, `model`, `metric`).** It is created with `CREATE UNIQUE INDEX IF NOT EXISTS`, so Step 003 databases gain it without `ALTER TABLE` or a migration. A test covers that case.
- **Live saves stay a plain `INSERT`.** They don't use `INSERT OR IGNORE`, so the CLI can never say "Saved" for a row that was silently dropped.
- **The seed command refuses `prod`**, which keeps simulated rows out of a production database.

## Alternatives / tradeoffs

- **A `source` column** (seeded vs. live) would label rows explicitly, but needs `ALTER TABLE` on existing databases. Left out as the larger change.
- **A window relative to "now"** keeps history current, but makes timestamps vary between runs and complicates the duplicate check.
- **The spike count is fixed at 5** by sampling hours, which keeps the spike tests deterministic.

## Limitations / review questions

- The fixed week gets older over time; a "last 7 days" view will eventually show none of it.
- Seeded and live dummy rows can only be told apart by timestamp.
- The unique index also applies to live inserts: two in the same microsecond would fail. This is not realistic for a single process.
