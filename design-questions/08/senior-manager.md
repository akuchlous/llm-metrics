# Step 08 — Senior manager

**Step context:** Step 008 measured total response latency (`total_latency`) alongside TTFT from one streamed request, saved both as separate rows in one transaction, and added a TTFT / Total latency selector to the time-window dashboard.

**Question:** This step renamed internal APIs (`measure_ttft` → `measure_latency`, `save_observation` → `save_observations`) and changed the CLI output. How do you decide whether that's acceptable churn, and how do you keep it reviewable?

## Answer

The test is **who depends on it**. Every caller of the renamed functions is inside this repo (the CLI and the tests), and no external package or user imports them; `D003` says the project isn't packaged. Keeping the old names would mean a misleading module (`ttft.py` measuring total latency) or compatibility shims nobody uses, so a clean rename was cheaper to maintain.

To keep it reviewable:

- The renames were done with `git mv`, but the files were also largely rewritten, so git shows them as delete-and-add. The step report lists each rename explicitly so reviewers don't have to infer it.
- All call sites were updated in the same commit, and a grep confirmed no stale references.
- The CLI's printed output (a human interface, but one that `run.sh` tests assert on) changed in the same commit as its tests (`Saved 2 observations`), and is documented in the README and the step report.
- The stable contract, `./run.sh` (D011), kept working; the end-to-end test proves it, with updated row counts (170 → 172).

## Critique

- **Good:** It applies "no compatibility for non-existent consumers" deliberately, and the contract that matters is protected by tests.
- **Weak:** The CLI output is half an interface. Someone could already be grepping `Saved observation to` in a script, and nothing distinguishes stable from unstable output. The report lists the renames, but the commit message doesn't flag them as breaking, and a rename combined with a rewrite in one commit is harder to review than a pure rename commit followed by the change.
- **Improve:** State which outputs are stable (e.g. "only `./run.sh` behaviour and the database schema are contracts; CLI text is not") in `DECISIONS.md`. When a machine-readable output is needed, add an explicit format (e.g. JSON) instead of parsing human text. Split renames into their own commit so the history shows them as renames.
