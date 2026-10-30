# Step 04 — Senior manager

**Step context:** Step 004 added a command that seeds 168 deterministic hourly simulated TTFT rows for a fixed week, idempotently via a unique index and `INSERT OR IGNORE`.

**Question:** Simulated data now looks realistic on a chart. How do you manage the risk of it being mistaken for real data?

## Answer

Defence in depth, from storage to screen:

1. **Data model:** every seeded row is `environment = 'test'`, enforced by a `CHECK` constraint.
2. **Command guard:** the seeder refuses to run unless `APP_ENV=test` (D024), and `./run.sh` never seeds in `prod`.
3. **Production guard:** `prod` can't run with the dummy provider at all (D008).
4. **UI:** the dashboard shows a prominent `TEST / SIMULATED DATA` label and "Not real LLM performance".
5. **Docs:** the README and status file state that current data is simulated.

## Critique

- **Good:** No single control is relied on. The guards are tested: the seeder refuses `prod`, and `prod` in `run.sh` creates no database.
- **Weak:** Exports leak context. When the owner printed the dashboard to PDF, the label lost its background colour and became faint grey text. Screenshots don't carry the `environment` field, and nothing marks simulated data in images.
- **Improve:** Make the label survive printing (`print-color-adjust: exact`) and add a visible watermark on the chart itself. Adopt a rule that no simulated chart goes into external material. Test the print and export paths, not just the browser view.
