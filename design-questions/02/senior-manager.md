# Step 02 — Senior manager

**Step context:** Step 002 added `./run.sh`: one command that creates/reuses `.venv` (without pip), runs all tests, and only if they pass runs the TTFT measurement.

**Question:** The rule is "never leave the repo in a state where `./run.sh` doesn't work". How do you enforce it?

## Answer

Through three layers, honestly labelled by strength:

1. **Automatic, local:** `./run.sh` runs the full suite and refuses to measure if any test fails, so a developer can't use a broken build without noticing.
2. **Automatic, in tests:** an end-to-end test runs `./run.sh` itself in a temporary copy (fresh venv, re-run, failing-test path, `prod` path), so the contract command is tested, not just the code.
3. **Process:** each step must run tests and `./run.sh` before committing, and an independent review happens before the next step.

What's *not* in place: nothing blocks a broken commit from reaching `main`. There's no CI and no branch protection, and docs commits are pushed directly.

## Critique

- **Good:** The contract is tested end to end, which most projects never do for their run script. The rule is written down as a decision (D011), so it survives changes of people and agents.
- **Weak:** Enforcement on `main` depends on discipline. It has held, but it's a single point of failure: one hurried commit breaks the contract for everyone who pulls.
- **Improve:** Add a minimal CI job (run the unit tests on push) and protect `main` once there's more than one contributor. Until then, say explicitly that the guarantee is "tested locally before each commit", not "enforced".
