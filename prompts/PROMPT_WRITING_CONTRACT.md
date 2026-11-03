# Numbered prompt authoring contract

This document is the reusable checklist for **ChatGPT when writing each numbered Claude implementation prompt**. Claude should also read it before executing each step. This complements (does not replace) `CODING_GUIDELINES.md`, `prompts/DESIGN_QUESTIONS.md`, `DECISIONS.md`, and `PROJECT_STATUS.md`.

## Canonical sources and roles

- `prompts/chatgpt-conversation.md`: **append-only history** of the user's evolving thinking, including superseded ideas and why direction changed. Never delete, reorder, silently correct, or rewrite prior text. Append a dated entry for each new prompt/decision.
- `DECISIONS.md`: current and historical architectural decisions with rationale; supersede explicitly rather than erase history.
- `PROJECT_STATUS.md`: current state, known limitations, next approved step.
- `CODING_GUIDELINES.md`: required correctness, security, readability, dependency reuse, testing and style rules.
- `prompts/DESIGN_QUESTIONS.md`: authoritative four-role design-question format and completion requirement.
- `design-questions/README.md`: learning-material index conventions.
- `prompts/<step>-output.md`: evidence of the actual implementation/analysis, tests, risks and next recommendation.

## Every new prompt must explicitly contain

1. **Identity and status:** precise step identifier (for example `018c`), descriptive title, current/pending status, previous step's evidence, and a single dominant objective.
2. **Required reading:** this contract, `CODING_GUIDELINES.md`, `prompts/DESIGN_QUESTIONS.md`, `DECISIONS.md`, `PROJECT_STATUS.md`, latest step output, conversation evolution log, and the actual relevant implementation/tests.
3. **Scope boundaries:** explicit in-scope tasks and *out-of-scope* work; one small incremental, reviewable change, no speculative refactoring.
4. **Invariants:** exact model/profile/workload, TTFT boundary, provider-authoritative usage, unknown ≠ zero, cached facts, request IDs, stored price basis, atomicity, simulated/real separation, no hidden retries/fallback/routing, security/privacy as applicable. Retain only the invariants relevant to that step; do not silently relax them.
5. **Safety and cost:** default offline tests; never call paid providers or create cloud resources without explicitly authorized, bounded step; keys and DB credentials never committed/logged; operational spend target $10/day including infrastructure when applicable.
6. **Quality:** focused regression tests and full offline suite, `./run.sh`, coding/style review, no unsupported success claims. Distinguish actual integration evidence from simulated/compiled/mock evidence.
7. **Design learning:** **explicitly reference `prompts/DESIGN_QUESTIONS.md` and require `design-questions/<step>/lead-engineer.md`, `principal-engineer.md`, `senior-manager.md`, `director.md` for every implemented numbered micro-step**. Questions must have context, actual grounded answer, and critique; four different role-appropriate concerns. Include a concise Design Q&A in the step's output and update the index if necessary. Analysis-only steps should still create role-specific decision questions when meaningful; if no design decision was made, document the explicit exception for ChatGPT review rather than silently omitting them.
8. **Evidence/report:** `prompts/<step>-output.md` with files changed, decisions, results, test counts, known gaps, spending/provider calls (including explicit none), commit SHA where available, one recommended next micro-step, and a brief **MARKETING CHECKPOINT** (including 'not publishable yet' when appropriate).
9. **History and stopping:** append—never edit old entries—in `prompts/chatgpt-conversation.md`; update current-status docs as needed; commit exactly this step and stop for ChatGPT review before starting the next. Do not rewrite an in-progress or completed numbered prompt retroactively.

## ChatGPT pre-publication checklist

Before committing a prompt to GitHub, check it against every item above, particularly **four design-question files**, append-only evolution log, output artifact, no paid calls by default, and stop/review boundary. Before declaring a step complete, inspect actual repository evidence and check the required artifacts exist. If anything was missed in a past step, issue a narrow corrective follow-up rather than rewriting the original historical prompt.

## Product sequencing context (as of 2026-11-03)

Prove an end-to-end, bounded, durable **OpenAI-only** LLM Metrics measurement pipeline before onboarding Anthropic, Google, xAI, or DeepSeek. `LLM Metrics` measures; future `LLM Router` executes/routs with EXACT or AUTO modes; `LLM Xchange` is a later market layer. Do not prematurely build Router or Xchange. Existing Google Cloud project identifier for deployment planning: `llm-metrics-513617` (never create a new project automatically). Each deployment/cost/price decision must be confirmed when relevant rather than assuming earlier estimates remain accurate.
