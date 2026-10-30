# Step 006 — TTFT percentiles

## Lead engineer: Why nearest-rank percentiles, and what was the bug risk in implementing them?

**Sample answer:** Nearest-rank returns an actually observed value, is deterministic, is easy to verify by hand, and handles a single observation. The risk was floating-point error: `ceil(0.07 * 100)` is 8, not 7, so we compute the rank as `(p * n + 99) // 100` with integers, and test p=7 with n=100.

- **Good:** A concrete justification and a concrete, tested pitfall.
- **Weak:** Doesn't acknowledge nearest-rank's main weakness: with small samples it is coarse and jumpy. With fewer than 100 observations, p99 is just the maximum, so one outlier swings it completely. Doesn't compare it with what other tools report (many use interpolation), which matters when comparing numbers across tools.
- **Improve:** State the tradeoff in one line: "honest observed values versus smoothness." Display the sample size next to the percentiles, and set a minimum sample size before showing p99 (for example, n ≥ 100). Name the method on the page (already done) so readers can compare correctly.

## Principal engineer: The percentiles are computed over the seeded week plus live runs together. Is that statistically sound?

**Sample answer:** It's the same data as the chart, so the numbers are consistent with what the user sees.

- **Good:** Values consistency between the chart and the summary.
- **Weak:** Mixing populations distorts the result. The seeded week has injected spikes, and live runs are about 100 ms each, so p99 describes the synthetic spikes, not live behaviour. It also misses time-window semantics: percentiles from different windows can't be averaged or combined, so any future "daily p95" has to be computed from raw data or a mergeable sketch.
- **Improve:** Say that the summary is only meaningful over one coherent population and time window. Recommend filtering by source and time before computing. If aggregation is needed at scale, store raw values or use a mergeable structure (histograms, t-digest), never averaged percentiles. Mention coordinated omission as a future concern when measuring under load.

## Senior manager: This step reversed an earlier decision ("`./run.sh` never seeds"). How should teams handle reversing decisions?

**Sample answer:** We updated D024 in place rather than adding a contradictory decision, and explained the new behaviour.

- **Good:** Keeps the decision log coherent and avoids two conflicting rules.
- **Weak:** Updating in place loses the history of why it changed: a reader of `DECISIONS.md` can no longer see that the opposite was once decided, or why. Git history has it, but people rarely look there.
- **Improve:** Keep the log concise, but record the reversal briefly (for example, "Revised in Step 006: run.sh now seeds in test, because a fresh clone showed an empty graph"). Reversals are healthy when driven by evidence; make that evidence visible.

## Director: Which latency number should be the headline when comparing providers: p50, p95, or p99?

**Sample answer:** p95. It reflects what most users experience without being dominated by rare outliers.

- **Good:** Picks a defensible middle ground and gives a reason.
- **Weak:** One headline number hides the shape of the distribution. Different audiences need different numbers: interactive chat users feel tail latency (p95/p99), while batch users care about p50 and throughput. A single number also invites providers to optimise for it.
- **Improve:** Headline p50 and p95 together, with p99 and the sample size available, all under a published method. Tie the choice to user scenarios (chat vs. batch), and commit to keeping the metric definitions stable so comparisons across time stay valid.
