# Step 01 — Director

**Question:** Why invest in a tool that, today, only measures a fake provider? What's the risk?

## Answer

The investment buys **de-risked methodology and plumbing before spending on real API calls**. The dummy provider lets us build and verify the measurement boundary, environment safety, storage, and presentation with no API cost, no credentials, and fully deterministic tests. When real providers arrive, only the provider adapter is new; everything else is already tested.

The main strategic risk is **credibility**. The product is *independent, trustworthy* numbers, and one simulated chart circulated as if it were real would damage that. We mitigated this from day one: `prod` refuses to run without a real provider (D008), every stored row carries its `environment`, and the dashboard labels data as TEST / SIMULATED.

## Critique

- **Good:** Safety is built into the architecture, not just the docs. The `prod` guard and the environment labelling have held for six steps.
- **Weak:** The connection to the business goal is implicit. There's no stated date or milestone for the first real measurement, so the dummy phase could stretch indefinitely. And printed or exported charts lose some of the labelling (the label's background disappeared when printed).
- **Improve:** Set an explicit "first real data" milestone and budget (API spend, credentials owner). Write a one-paragraph data-provenance policy: every exported number or image must carry its environment and source.
