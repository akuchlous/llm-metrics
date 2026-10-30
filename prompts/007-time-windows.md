# Step 007 — TTFT time windows

Read `PROJECT_STATUS.md`, `DECISIONS.md`, and `prompts/README.md` first. Preserve the existing Step 006 behavior unless this prompt changes it.

## Goal

Let the local dashboard view TTFT over a selected **24h, 7d, or 30d** time window, with the chart and p50/p95/p99 computed from exactly the same selected observations.

## Requirements

- Add simple server-rendered controls/links for `24h`, `7d`, and `30d`; no JavaScript or new dependency.
- Define each window relative to **current UTC time**, not relative to the newest stored observation. Document boundary semantics explicitly (for example, whether the cutoff itself is included) and use them consistently.
- Filter observations in the data-access layer rather than loading all rows and filtering in HTML/rendering code. Keep SQL values parameterized.
- The selected window must drive all displayed derived data: observation count, first/latest timestamps, chart, and p50/p95/p99. Never calculate percentiles from a different population than the chart.
- Choose one of `24h`, `7d`, or `30d` as the default and document why. Invalid window input must fail safely or fall back explicitly; do not silently interpret arbitrary values.
- Preserve the empty-state behavior when a valid selected window has no observations.
- Keep the existing fixed simulated history and idempotent seeding unchanged. It is acceptable for old seeded data to fall outside a real wall-clock window; do not distort time-window semantics to keep demo data visible.
- Keep the dashboard bound to `127.0.0.1` with the existing CSP.

## Acceptance

Add focused tests proving:

- cutoff filtering is correct, including the boundary;
- 24h/7d/30d select different populations from controlled timestamps;
- chart/count/p50/p95/p99 all use the selected population;
- empty valid windows render cleanly;
- invalid window input has the documented behavior;
- existing dashboard/server/security behavior still works;
- `./run.sh` remains working and the full test suite passes.

Prefer deterministic tests with an explicit/fixed notion of `now`; do not make tests depend on the machine clock.

## Design Q&A

In `prompts/007-output.md`, include a concise **Design Q&A** section with 3–5 technical questions and answers grounded in this implementation. At minimum cover:

1. Why should time filtering happen in the storage/query layer rather than after loading every observation?
2. Why must the chart and percentiles use exactly the same population?
3. What clock/boundary semantics were chosen, and what would break if they were ambiguous?

Include tradeoffs and alternatives, not just descriptions of the code.

## Out of scope

Do not add new metrics, real providers, workload/region dimensions, scheduled jobs, aggregate tables/sketches, authentication, JavaScript, or schema changes unless a schema change is strictly necessary for this step (it should not be).

Do not redesign the fixed Step 004 seed data merely to make every time window visually populated.

## Stop

Update `PROJECT_STATUS.md` and only durable decisions in `DECISIONS.md`. Save the concise implementation/design report as `prompts/007-output.md`, commit the completed step, and stop. Do not begin Step 008.
