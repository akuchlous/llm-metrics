# Development prompts

This directory is the historical record of the micro-step prompts used to develop `llm-metrics`.

## Convention

Prompts are numbered in execution order:

```text
001-initial-ttft.md
002-local-run-script.md
003-...
```

Once a prompt has been used, treat it as **immutable history**. Do not edit an old prompt to reflect later architecture or decisions. Add a new numbered prompt instead.

Before implementing a step, the coding agent should read:

1. `PROJECT_STATUS.md` — current source of truth for implementation status.
2. `DECISIONS.md` — architectural/project decisions.
3. The numbered prompt for the requested step.
4. `prompts/chatgpt-conversation.md` when broader product/project context is useful.

Each development step should be small, independently testable, preserve all previously working functionality, update `PROJECT_STATUS.md`, and stop before implementing the next numbered step.
