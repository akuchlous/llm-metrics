# Development prompts

Number prompts in execution order. Once used, a prompt is immutable history.

Before a step, read:
1. `PROJECT_STATUS.md` — current state.
2. `DECISIONS.md` — shared engineering rules and durable decisions.
3. The current numbered prompt.

## Prompt standard

Prompts follow the same principles as code: clear, maintainable, simple, and no bloat.

Use only what the step needs:

1. **Goal** — one concrete outcome.
2. **Requirements** — only step-specific behavior and constraints.
3. **Acceptance** — focused tests and observable success criteria.
4. **Out of scope** — only likely scope mistakes.
5. **Stop** — do not start the next step.

Do not repeat rules already in `DECISIONS.md` or current state already in `PROJECT_STATUS.md`; reference those files instead. Avoid long checklists, duplicated requirements, speculative future design, and verbose final-report instructions.

Each step must preserve existing behavior, update `PROJECT_STATUS.md`, record only durable new decisions in `DECISIONS.md`, and stop for independent review.

## Step report

At the end of every step, save Claude's concise implementation report as `prompts/NNN-output.md` and include it in the step commit. The report should capture:

- what changed;
- tests/run result;
- design decisions and tradeoffs;
- known limitations or review questions.

Keep it concise. It is a historical record, not a duplicate of `PROJECT_STATUS.md`.
