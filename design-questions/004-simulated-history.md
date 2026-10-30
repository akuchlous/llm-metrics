# Step 004 — Deterministic simulated history

## Lead engineer: How is re-seeding made idempotent? Compare it with the alternatives.

**Sample answer:** A unique index on (`recorded_at`, `environment`, `provider`, `model`, `metric`) plus `INSERT OR IGNORE`. Re-running inserts zero rows. The index is created with `IF NOT EXISTS`, so databases from Step 003 gain it without a migration.

- **Good:** A database-enforced guarantee, compatible with existing databases, with a test for the old-schema case.
- **Weak:** Doesn't compare the alternatives. A `source` column (seeded vs. live) would make provenance explicit but needs `ALTER TABLE`. A "seeded" marker table is simple, but can drift from the actual rows. Also misses a side effect: the unique index now applies to live inserts too, and live saves deliberately use a plain `INSERT`, so a (practically impossible) same-microsecond collision would raise an error rather than be silently dropped.
- **Improve:** Present the decision as a comparison: what each option costs and why the index won (smallest change, no migration). State the side effect on live inserts and why it is acceptable.

## Principal engineer: The history uses a fixed calendar week, not "the last 7 days". Defend or attack that.

**Sample answer:** A fixed window is fully reproducible: same rows on every machine, and trivial idempotence. A relative window would change on every run.

- **Good:** Correctly prioritises determinism for test data.
- **Weak:** Ignores the downside that showed up later: the data ages, so any "recent" view will eventually show none of it, and the dashboard had to avoid time windows because of it (D027). The determinism argument also only needs a fixed seed for the values; timestamps could be relative and still deterministic if each one is computed from a stable anchor.
- **Improve:** Separate the two properties: deterministic values (fixed seed) and stable timestamps (fixed anchor). Explain why both were fixed (simplest idempotence) and what that costs (stale data, constraints on later queries). Name the trigger to revisit: the first time-window feature.

## Senior manager: Simulated data now looks realistic on a chart. How do you manage the risk of it being mistaken for real data?

**Sample answer:** Every row is `environment = 'test'`, the seeder refuses `prod`, and the dashboard shows a big TEST / SIMULATED DATA label.

- **Good:** Defence in depth: the data model, the command guard, and the UI.
- **Weak:** Screenshots and PDFs travel without context; the label even lost its background colour when printed (noted after Step 005). Nothing marks the data when it leaves the dashboard.
- **Improve:** Treat provenance as part of every export: a watermark on images and PDFs, `environment` on every exported row, and a review rule that no simulated chart goes into external material. Test the label in print and screenshot paths too.

## Director: Why spend engineering time generating fake history instead of collecting real measurements?

**Sample answer:** The dashboard needs data to design against, and real measurements cost money and need credentials. Fake data unblocks the UI work.

- **Good:** A clear unblocking rationale and cost awareness.
- **Weak:** Doesn't bound the investment, or say when it stops being useful. Synthetic data can bias design: the spikes are hand-picked and real latency distributions have long tails, so a UI tuned to fake data may mislead on real data.
- **Improve:** Time-box synthetic work, and set a milestone where real data replaces it. Validate the synthetic distribution against a small sample of real measurements as soon as one provider exists.
