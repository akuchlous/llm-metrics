# Development prompts

## Purpose

This directory is the implementation history and handoff contract for the step-by-step development of `llm-metrics`.

Each numbered prompt defines one small implementation step for Claude. Its matching `NNN-output.md` records what was actually implemented, tested, decided, and left for later. Once a prompt has been used, it is immutable history.

Supporting files in this directory contain reusable prompt rules and project-direction context; numbered prompts should reference those shared files rather than duplicate them.

## Workflow

Number prompts in execution order. Before a step, read:
1. `PROJECT_STATUS.md` — current state.
2. `DECISIONS.md` — shared engineering rules and durable decisions.
3. `prompts/DESIGN_QUESTIONS.md` — required design-question output for each step.
4. The current numbered prompt.

## Prompt standard

Prompts follow the same principles as code: clear, maintainable, simple, and no bloat.

Use only what the step needs:

1. **Goal** — one concrete outcome.
2. **Requirements** — only step-specific behavior and constraints.
3. **Acceptance** — focused tests and observable success criteria.
4. **Out of scope** — only likely scope mistakes.
5. **Stop** — do not start the next step.

Do not repeat rules already in `DECISIONS.md`, `prompts/DESIGN_QUESTIONS.md`, or current state already in `PROJECT_STATUS.md`; reference those files instead. Avoid long checklists, duplicated requirements, speculative future design, and verbose final-report instructions.

Each step must preserve existing behavior, update `PROJECT_STATUS.md`, record only durable new decisions in `DECISIONS.md`, create the required design-question files, and stop for independent review.

## Step report

At the end of every step, save Claude's concise implementation report as `prompts/NNN-output.md` and include it in the step commit. The report should capture:

- what changed;
- tests/run result;
- **choices made**: every decision taken during the step, both the questions asked before implementing (options offered and the answer) and the choices made during implementation (with the reason);
- design decisions and tradeoffs;
- known limitations or review questions.

Keep it concise. It is a historical record, not a duplicate of `PROJECT_STATUS.md`.
