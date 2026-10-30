# Step 006 — TTFT percentiles

Read `PROJECT_STATUS.md`, `DECISIONS.md`, and `prompts/README.md` first. Follow their engineering rules.

## Goal

Add p50, p95, and p99 TTFT summaries to the existing dashboard, and make the test-mode one-command experience populate simulated history automatically.

## Requirements

- Compute p50, p95, and p99 from the same observations currently displayed by the dashboard.
- Use one explicit, documented percentile method with deterministic behavior for small datasets; keep the calculation independent of HTML rendering.
- Show the three percentile values clearly near the existing latest-TTFT summary.
- Handle empty and single-observation datasets cleanly.
- In `APP_ENV=test`, `./run.sh` must run the existing idempotent history seeder before the live measurement so a fresh clone gets a meaningful graph and percentile summary.
- Never seed in `APP_ENV=prod`; preserve the existing safe production failure behavior.
- Update D024 or related documentation to reflect the new orchestration behavior rather than adding a contradictory decision.
- Do not change the observation schema.

## Acceptance

Tests must verify:

- p50/p95/p99 against small known datasets using the chosen documented method;
- percentile results are independent of observation timestamp order;
- empty and single-value behavior;
- dashboard displays the calculated percentile values from stored observations;
- repeated test-mode `./run.sh` executions do not duplicate the 168 seeded rows;
- production mode never seeds simulated history;
- existing tests still pass and `./run.sh` remains the local one-command experience.

Avoid testing cosmetic HTML details beyond the user-visible metric values/labels.

## Out of scope

No new metric, time-range filter, real provider, scheduler, schema redesign, workload dimensions, execution-location dimensions, or new dependency.

## Stop

Run the full tests and `./run.sh`, perform the required security/readability/bloat review, update project docs, save the concise report as `prompts/006-output.md`, commit Step 006, and stop. Do not implement Step 007.