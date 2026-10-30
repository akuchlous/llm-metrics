# Step 07 — Senior manager

**Step context:** Step 007 added 24h / 7d / 30d time windows to the dashboard (`/?window=`, default 7d), filtered in SQL relative to current UTC with inclusive bounds, so the count, chart, and p50/p95/p99 all come from the same rows.

**Question:** This step reversed an earlier decision (D027, "no time window") and introduced behaviour that changes with the calendar. How do you keep the team, and reviewers, from being surprised?

## Answer

Three things:

1. **Make reversals visible.** D027 was revised in place with a one-line note: "Revised in Step 007: originally showed all rows with no window so the fixed seeded week stayed visible…". The decision log stays coherent, and the history is still readable without digging through git. That applies the lesson from the Step 06 senior-manager question.
2. **Put time-dependent behaviour in writing with a date.** `PROJECT_STATUS.md` and the step report say exactly when the seeded week leaves every window (2026-11-28 23:00 UTC), so "the chart went empty" is a known event, not a bug report.
3. **Keep tests independent of the calendar.** Tests use a fixed `NOW`. The `run.sh` end-to-end test no longer asserts exact counts, which would have started failing on a future date; it checks the default window is selected and that the live row is present.

## Critique

- **Good:** No future-dated test failure is baked in, and the date-based change in behaviour is announced in advance.
- **Weak:** The announcement lives in docs that people read only when something looks wrong. There's no in-product hint: on an empty 7d view, the page doesn't say that older simulated data exists in 30d, or that it has aged out entirely.
- **Improve:** When a window is empty but older rows exist, say so on the page ("older observations exist; try 30d"). It's a small, honest UX touch. Add a recurring review item: "check time-dependent behaviour and dates in docs" at each step review.
