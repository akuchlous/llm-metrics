# Step 05 — Senior manager

**Step context:** Step 005 added a stdlib-only local dashboard on `127.0.0.1` (HTML + server-rendered SVG chart, no JavaScript), started at the end of `./run.sh`.

**Question:** `./run.sh` changed from "runs and exits" to "keeps serving until Ctrl+C". How do you handle a behaviour change like that?

## Answer

Treat it as a breaking change to a contract (D011), because `./run.sh` is the project's primary interface. What we did:

- Recorded it as a decision (D029) and in the README's run instructions.
- Called it out in the Step 005 report under review questions ("anything that used it as a run-and-exit command must change").
- Updated the end-to-end test to the new contract: read output until the `Dashboard:` line, fetch the page, then terminate. A watchdog kills it after 120 s so the suite can't hang.
- Kept the failure paths unchanged: failed tests, or `prod`, still exit non-zero before the dashboard starts.

## Critique

- **Good:** The change was documented, tested, and reviewable, and the safety paths were explicitly preserved.
- **Weak:** No one checked who depended on the old behaviour; we assumed there were no consumers because there's no CI. The commit message didn't flag it as breaking.
- **Improve:** Mark contract changes clearly ("BREAKING:" in the commit and the report), and check consumers first: CI, scripts, docs, habits. If a run-and-exit consumer appears, add an explicit mode for it rather than reverting the experience.
