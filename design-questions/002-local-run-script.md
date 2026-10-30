# Step 002 — One-command local run (`./run.sh`)

## Lead engineer: Why does `run.sh` create the venv with `--without-pip`, and what does that cost?

**Sample answer:** On Debian, which Chromebook Linux uses, `python3 -m venv` fails unless the `python3-venv` package is installed. We have no dependencies, so we don't need pip, and skipping it makes the script work out of the box.

- **Good:** Ties the choice to a real environment failure, not to taste.
- **Weak:** Doesn't spell out the cost. The first dependency forces a change to `run.sh` and to the setup instructions, and contributors who `pip install` into `.venv` will be confused. It also doesn't mention that the venv currently provides little isolation: no dependencies means it mostly pins the interpreter.
- **Improve:** State the cost and the trigger: "the first dependency requires `ensurepip` or `python3-venv`; the README must change then." This is recorded as D012; reference it so the debt is visible, not tribal knowledge.

## Principal engineer: `run.sh` runs the whole test suite before every run. Is that a good long-term design?

**Sample answer:** Yes. It guarantees nobody runs a broken build, and the suite is fast.

- **Good:** Values the "always working" contract.
- **Weak:** "The suite is fast" holds only for now; it grew from about 1.5 s at Step 002 to about 8 s by Step 006. The end-to-end test also needs a recursion guard (`LLM_METRICS_INSIDE_RUN_SH_TEST`), which is a smell: the run command and the verification command are tangled together.
- **Improve:** Separate concerns before it hurts: `./run.sh` runs a fast smoke subset, and a `check` command or CI runs the full suite. Set a time budget (e.g. under 10 s locally) that triggers the split. The recursion guard is acceptable now, but should be flagged as debt.

## Senior manager: The rule is "never leave the repo in a state where `./run.sh` doesn't work". How do you enforce it?

**Sample answer:** `run.sh` runs the tests, so a broken change is caught immediately, and every step is reviewed before the next one starts.

- **Good:** Uses existing mechanisms: tests and the review gate.
- **Weak:** Enforcement depends on people remembering to run it. Nothing stops a commit that breaks `run.sh` from reaching `main`, and docs-only commits are pushed directly too.
- **Improve:** Add automated enforcement when it's justified: a CI job that runs `./run.sh`'s test stage on every push, plus branch protection. Until then, say plainly that the rule is enforced by review discipline, so nobody overestimates the guarantee.

## Director: The reference developer machine is a Chromebook. What are the implications for an open-source project?

**Sample answer:** It's a low bar, so if it works on a Chromebook it works almost anywhere. It keeps the stack simple.

- **Good:** Sees that the constraint drives simplicity, which is good for adoption.
- **Weak:** "Works anywhere" is unproven: only Linux plus bash is tested, not macOS or Windows. It also skips the strategic tradeoff: some contributors expect Docker or `make`, and the project deliberately has neither.
- **Improve:** State the supported platforms explicitly, and decide whether macOS and Windows matter for the target contributors. If they do, add them to CI before claiming support. Treat "one command on a cheap laptop" as a deliberate selling point for credibility and reproducibility.
