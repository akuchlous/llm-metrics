# Step 005 — First local TTFT dashboard

Read `PROJECT_STATUS.md`, `DECISIONS.md`, and `prompts/README.md` first. Follow their engineering rules.

## Goal

Display the existing simulated TTFT observations in a minimal local browser dashboard.

## Requirements

- Add the smallest justified web dependency and implementation needed for a local dashboard.
- Serve only on `127.0.0.1` by default.
- Read existing SQLite observations; do not change the observation schema in this step.
- Show:
  - project title;
  - provider and model;
  - a prominent `TEST / SIMULATED DATA` label;
  - a TTFT-over-time line graph using the seeded history;
  - the latest TTFT value.
- The fixed Step 004 history must remain visible even when it is older than the current date; do not label it `last 7 days` unless the query actually represents the current last seven days.
- Keep data access separate from HTTP/view rendering with only the minimum structure current requirements justify.
- `./run.sh` must remain the one-command local experience: preserve tests and measurement, then leave the dashboard running and print its local URL.
- Handle an empty database cleanly rather than failing.
- Update documentation only where behavior or a durable design decision changes.

## Acceptance

Tests must verify:

- dashboard data is read from SQLite rather than hard-coded;
- only the intended `test` / dummy / `ttft` observations are displayed;
- observations are ordered by timestamp;
- the simulated/test label is present;
- empty data produces a valid page/state;
- the server defaults to `127.0.0.1`;
- existing tests still pass;
- `./run.sh` still works and prints the dashboard URL.

Use temporary databases in tests. Avoid tests that depend on a real browser or external network.

## Out of scope

No new metrics, percentiles, filters, real providers, scheduler, cloud deployment, authentication, ORM, frontend framework, or observation-schema redesign.

Do not yet add workload dimensions such as request category/token sizes or execution location/cloud/zone. These are known future benchmark dimensions and should be designed when real benchmarking requires them.

## Stop

Run the full tests and `./run.sh`, perform the security/readability/bloat review required by `DECISIONS.md`, update project docs, save the concise report as `prompts/005-output.md`, commit Step 005, and stop. Do not implement Step 006.