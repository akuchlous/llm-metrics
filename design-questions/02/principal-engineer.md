# Step 02 — Principal engineer

**Question:** `run.sh` runs the whole test suite before every run. Is that a good long-term design?

## Answer

It's the right design for now and the wrong one later. Today the run command doubles as the safety gate. There's no CI, so running tests on every `./run.sh` is the only automatic guarantee that the local contract ("`./run.sh` always works", D011) holds. The suite is small, standard-library only, and fast.

It degrades predictably:

- **Time.** The suite grew from about 1.5 s at Step 002 to about 8 s at Step 006, mostly from the end-to-end test creating a venv. A run command that gets slower every step is friction.
- **Coupling.** The end-to-end test calls `run.sh`, which runs the suite that contains that test. It needs a recursion guard (`LLM_METRICS_INSIDE_RUN_SH_TEST`), a clear sign that "run" and "verify" are tangled.

The long-term shape: `./run.sh` runs a fast smoke subset, and a separate check command (and CI) runs everything.

## Critique

- **Good:** It made breakage impossible to miss during early development, and the end-to-end test verifies the real one-command experience, including failure paths.
- **Weak:** The recursion guard is test-only code in production paths. Runtime grows with every step, and there's no budget or trigger for splitting.
- **Improve:** Set an explicit budget (e.g. under 10 s for `./run.sh` before the measurement starts). When it's exceeded, split the commands and move full verification to CI. Remove the recursion guard at the same time.
