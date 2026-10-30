# Step 01 — Senior manager

**Step context:** Step 001 built a stdlib-only Python package that measures Time To First Token against a simulated streaming `DummyProvider`, with a `test`/`prod` switch (`prod` refuses to run) and a CLI.

**Question:** The team is told to build in "extremely small steps". How do you stop that becoming slow, or becoming overbuilding by stealth?

## Answer

The controls are written down, not cultural:

- **A numbered prompt per step**, with Goal, Requirements, Acceptance and **Out of scope** sections. The out-of-scope list is the main defence against stealth overbuilding.
- **A required report** (`prompts/NNN-output.md`) and an updated `PROJECT_STATUS.md`, so every step ends with a reviewable record.
- **An independent review gate** before the next prompt is written (`DECISIONS.md`).
- **A quality order** that ranks correctness and security above minimal code, so "small" never means "sloppy".

To stop it becoming slow, each step must produce something observable: a printed number, a command, a page. Steps 001–006 went from no code to a dashboard with percentiles, each step independently testable.

## Critique

- **Good:** It worked. Every step was reviewable in minutes, scope creep was caught in writing, and decisions are traceable to steps.
- **Weak:** There's no explicit throughput goal or time box. Six steps in, there's still no real provider, and nothing in the process says when that must happen. Small steps optimise review cost, not time-to-value.
- **Improve:** Add a milestone horizon to `PROJECT_STATUS.md` (e.g. "first real TTFT measurement by step N"). Track elapsed time per step, and revisit step size once the foundations are stable. Later steps can be larger without losing reviewability.
