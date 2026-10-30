# Step 004 — Simulated TTFT history

Read `PROJECT_STATUS.md`, `DECISIONS.md`, and `prompts/README.md` first. Follow their engineering and prompt-development rules.

## Goal

Create deterministic historical simulated TTFT data so the next step can display a useful graph.

## Requirements

- Generate **168 observations**: one per hour for 7 days.
- Use the existing dummy provider/model, `ttft`, and `environment = 'test'`.
- Values should look plausible for test data: normal variation plus a small number of latency spikes.
- Generation must be deterministic/reproducible.
- Historical timestamps must be stored explicitly rather than using the current save time.
- Re-running the seed operation must not duplicate the simulated history.
- Reuse the existing SQLite storage design; make only the smallest storage change needed to support historical timestamps/idempotence.
- Keep simulated data clearly distinguishable from future production data.
- Provide a simple command to seed the history. Do not make normal TTFT measurement depend on seeding.
- Update `README.md`, `PROJECT_STATUS.md`, and `DECISIONS.md` only where the new behavior or a durable decision requires it.

## Acceptance

Tests must verify:

- exactly 168 historical observations are created;
- timestamps span 7 days at hourly intervals;
- values are deterministic and include variation;
- all seeded rows are `test` / dummy / `ttft`;
- running the seed operation again creates no duplicates;
- existing measurements still append normally;
- all existing tests pass;
- `./run.sh` still works.

Use temporary databases in tests.

## Out of scope

No dashboard, web server, charts, percentiles, new metrics, real providers, scheduler, Docker, cloud infrastructure, ORM, or migration framework.

Do not add abstractions or dependencies for future steps.

## Stop

Run the full tests and `./run.sh`, perform the security/readability/bloat review required by `DECISIONS.md`, update project docs, commit Step 004, and stop.

Report the commit SHA, files changed, test results, seed command/result, idempotence verification, and any design concern worth reviewing. Do not implement Step 005.