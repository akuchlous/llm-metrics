# Step 05 — Director

**Step context:** Step 005 added a stdlib-only local dashboard on `127.0.0.1` (HTML + server-rendered SVG chart, no JavaScript), started at the end of `./run.sh`.

**Question:** What would make this dashboard credible to people outside the team?

## Answer

For an independent benchmark, credibility comes from **methodology transparency and reproducibility** more than visuals.

What exists: honest labelling (TEST / SIMULATED), every number traceable to stored rows, open code, a one-command reproduction (`./run.sh`), and deterministic test data. The chart's time axis is proportional to real time, and the page says "All N observations, <first> to <last>" rather than implying a "last 7 days" window that doesn't exist.

What credibility will additionally need, once real data exists:

- A published methodology: TTFT boundary, prompts, regions, frequency, and connection reuse.
- Sample sizes and percentile methods shown next to every summary (the method name already is).
- A changelog of methodology changes, so trends across time stay comparable.

## Critique

- **Good:** Honesty is built into the UI and the data model, and reproducibility is unusually strong for an early-stage project.
- **Weak:** There's no methodology document yet, and the dashboard doesn't show where measurements come from (client location or network), which is a major driver of TTFT.
- **Improve:** Write `METHODOLOGY.md` before the first real provider ships, and link to it from the dashboard. Add measurement location as a dimension when real benchmarking needs it (already noted as a future dimension in the Step 005 prompt).
