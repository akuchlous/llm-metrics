# Step 04 — Director

**Question:** Why spend engineering time generating fake history instead of collecting real measurements?

## Answer

Because it unblocked the presentation work cheaply and safely. A graph and percentiles need weeks of data; real collection would need credentials, API spend, a scheduler, and calendar time just to have something to design against. A deterministic generator gave the dashboard 168 points in one step, with zero cost and no secrets.

The investment was bounded: about 75 lines including the command, values centred on the dummy's 100 ms so live and seeded data line up, and five fixed spikes that make the tail visible.

## Critique

- **Good:** A fast, cheap unblocker that enabled Steps 005 and 006, with no external dependencies or spending.
- **Weak:** Synthetic data biases design. Real TTFT distributions have long tails and daily patterns, while ours has Gaussian noise plus five hand-placed spikes. The percentile summary is effectively describing our own spike injection (see 06). There's no plan to retire or validate it.
- **Improve:** Time-box synthetic data with a replacement milestone. Once one real provider exists, collect a small real sample and check the dashboard's assumptions (scale, outliers, density) against it. Keep the generator only for tests.
