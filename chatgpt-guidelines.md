# ChatGPT guidelines for writing Claude implementation prompts

**Mandatory:** Before drafting, reviewing, or committing **every** new numbered Claude prompt, ChatGPT must read this file and its linked requirements from the GitHub repository. Do not rely on memory of the rules. This is a prompt-authoring contract for ChatGPT, not an instruction to implement project features.

## Read every time

1. `prompts/PROMPT_WRITING_CONTRACT.md` — the complete, current prompt-authoring checklist and completion gates.
2. `prompts/DESIGN_QUESTIONS.md` — exact four-role learning-artifact requirements.
3. `CODING_GUIDELINES.md` — programming/quality contract to include by reference in every prompt.
4. `PROJECT_STATUS.md` and `DECISIONS.md` — current implementation state and architectural history.
5. `prompts/chatgpt-conversation.md` — **append-only** record of the user's evolving plans.
6. Previous numbered prompt, its `-output.md`, and actual relevant code/tests before proposing the next step.

## Non-negotiable prompt-writing rules

- **One small micro-step at a time.** Specify exactly one objective, in-scope work, exclusions, test evidence, and stop-for-review boundary. Claude does not automatically proceed to the next step.
- **Explicit learning artifacts.** Every implemented step requires `design-questions/<step>/lead-engineer.md`, `principal-engineer.md`, `senior-manager.md`, and `director.md` with distinct questions, implementation-grounded answers and critiques. Include a short Design Q&A in the step output. For analysis-only steps, provide decision-focused learning questions when meaningful, or explain an explicit exception.
- **Outputs and reviews.** Require `prompts/<step>-output.md`, full offline tests, `./run.sh` where applicable, coding-guideline/style checks, evidence and limitations, commit, and **stop for ChatGPT review**.
- **Measurement invariants.** Preserve exact provider/model/request profile and versioned workload; no hidden retries/routing/fallback; valid TTFT and usage semantics; unknown is NULL, never fabricated zero; distinct real/test populations; saved price basis; privacy and atomic storage. Apply the relevant subset explicitly in each prompt.
- **Security and spending.** No API secrets, passwords, prompt/response content, or raw sensitive errors in source/logs. No cloud provisioning, paid model calls or recurring jobs unless the specific reviewed step explicitly authorizes bounded operations. Overall target budget is $10/day including provider APIs and infrastructure.
- **Knowledge and history.** GitHub is the source of truth. Never delete or rewrite older material in `prompts/chatgpt-conversation.md`: append dated explanations of what changed and why. Do not retroactively edit already-running/completed prompt files. Keep `PROJECT_STATUS.md` current.
- **Growth/learning checkpoint.** Every step report includes a concise marketing checkpoint, even if nothing is publishable yet. Keep product scope focused on finishing OpenAI-only LLM Metrics end-to-end before additional providers and future Router/Exchange features.

## Before committing a prompt

Check the complete checklist in `prompts/PROMPT_WRITING_CONTRACT.md`. Verify that the new prompt explicitly requires design questions, an output report, append-only history update, no paid calls by default, and stopping after one step. Then commit the prompt and append the decision/reason to the conversation-history file.

## After implementation

Read the actual code, tests, output report, design-question artifacts, and history update before approving the next prompt. Missing artifacts are follow-up work, not grounds to silently revise the old prompt.

**Rule of thumb:** The prompt must be usable by a new Claude session with no access to this ChatGPT conversation.
