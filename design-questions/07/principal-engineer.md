# Step 07 — Principal engineer

**Step context:** Step 007 added 24h / 7d / 30d time windows to the dashboard (`/?window=`, default 7d), filtered in SQL relative to current UTC with inclusive bounds, so the count, chart, and p50/p95/p99 all come from the same rows.

**Question:** Windows are anchored to the current UTC time, not to the newest observation, and the seeded week now ages out. Was that the right call?

## Answer

Yes. A window labelled "24h" has to mean the last 24 hours of real time, or the dashboard lies. Anchoring to the newest observation would show stale data as if it were current. If collection stopped two weeks ago, a newest-anchored "24h" view would still look healthy, hiding exactly the outage a monitoring view should reveal. The prompt also forbade distorting semantics to keep demo data visible.

The consequences were accepted explicitly:

- The fixed seeded week (2026-10-23 to 10-29) drops out of 24h and 7d first, and after 2026-11-28 23:00 UTC it's outside every window. The dashboard then shows only live runs.
- Empty windows are a normal state, rendered cleanly ("No observations in the selected window"), not an error.
- Tests can't use the real clock for assertions, so `build_page(db_path, window, now)` takes `now` as a parameter, and tests use a fixed `NOW`.

## Critique

- **Good:** Correct semantics over convenient demos, with the cost documented (README, the status file, D027's revision note) instead of discovered later.
- **Weak:** The fixed-anchor seed decision from Step 004 and the now-relative windows from Step 007 now conflict, and the demo degrades by a calendar date nobody will remember. The fix for that is a product decision that hasn't been made.
- **Improve:** Decide explicitly, in a future step, whether test mode should keep a populated demo. If so, generate history relative to a per-database anchor recorded at first seed (values still deterministic from the fixed seed). Don't solve it by bending window semantics.
