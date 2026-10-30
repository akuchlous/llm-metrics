# Step 06 — Senior manager

**Step context:** Step 006 added nearest-rank p50/p95/p99 TTFT to the dashboard and made `./run.sh` seed simulated history automatically in test mode (never in prod).

**Question:** This step reversed an earlier decision ("`./run.sh` never seeds"). How should teams handle reversing decisions?

## Answer

Reversal was the right call, driven by evidence: the owner's first dashboard on the Chromebook showed a flat line with 2 points, because a fresh clone had no history. The fix is that `./run.sh` seeds idempotently in `test` before measuring, and never in `prod`.

How we handled the record: the prompt explicitly said to update D024 in place rather than add a contradictory decision. D024 now states the new behaviour, and D029 shows the new order (tests → seed (test only) → measurement → dashboard). The Step 006 report and the commit message describe the change, and the end-to-end test proves `prod` never seeds and repeated runs don't duplicate rows.

## Critique

- **Good:** The decision log stays coherent (one current rule, not two conflicting ones). The reversal was triggered by real user feedback and protected by tests.
- **Weak:** Updating in place erases the visible history in `DECISIONS.md`. A reader can't see that the opposite was once decided, or why it changed, without digging through git.
- **Improve:** Keep a one-line revision note on reversed decisions, e.g. "Revised in Step 006: a fresh clone showed an empty graph." It stays concise but preserves the learning: why we were wrong, and what evidence changed our minds.
