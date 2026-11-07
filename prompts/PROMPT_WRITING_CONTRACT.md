# Claude prompt-writing contract (authoritative checklist)

Use this checklist **every time ChatGPT authors a numbered Claude prompt**. The root `chatgpt-guidelines.md` is only an entry point; maintain the detailed rules here, without duplicating them there.

## Read before drafting

- `PROJECT_STATUS.md`, `DECISIONS.md`: current state, constraints, prior decisions.
- `prompts/chatgpt-conversation.md`: append-only evolution of the user's thinking; never edit/reorder/delete older entries.
- Previous numbered prompt and `prompts/<previous-step>-output.md`, plus relevant **actual code/tests**.
- `CODING_GUIDELINES.md`: implementation quality, security, dependency reuse and style.
- `prompts/DESIGN_QUESTIONS.md` and `design-questions/README.md`: learning deliverables and index.

## Each numbered prompt must specify

1. **One reviewable micro-step:** identifier, narrow objective, evidence from previous step, explicit in-scope/out-of-scope boundaries. No unrelated refactors or starting the following step.
2. **Relevant invariants:** exact provider/model/request profile and workload; no hidden retries, routing or fallback; correctly bounded TTFT and authoritative tokens; unknown ≠ zero; cache provenance, request IDs, stored pricing, atomic writes, and distinct real/simulated populations. Include only the ones relevant to the change; never silently weaken them.
3. **Safety and cost:** offline tests by default; no paid provider calls, GCP resource creation, scheduled execution or secrets exposure without explicit, bounded authorization. Never log/store raw prompts, outputs, keys, credentials or sensitive error text. Total project target ≤ $10/day including infrastructure and API usage.
4. **Validation:** focused tests, full offline suite, `./run.sh` when applicable, and `CODING_GUIDELINES.md` style/quality review. Distinguish actual integration from mocked or dialect-compilation evidence.
5. **Design questions:** explicitly require `prompts/DESIGN_QUESTIONS.md` and four files under `design-questions/<step>/`: `lead-engineer.md`, `principal-engineer.md`, `senior-manager.md`, `director.md`. Each needs role-specific question, actual code/decision-grounded answer, and critique. Include concise Design Q&A in the output; update the index. For an analysis-only step, use decision-grounded questions where meaningful or document why an exception needs review.
6. **Completion artifacts:** `prompts/<step>-output.md` listing changes, decisions, evidence/test counts, limitations, whether paid calls/resources were used, commit SHA when available, **one** next recommendation, and a **marketing checkpoint** (including 'not publishable yet'). Update `PROJECT_STATUS.md`/`DECISIONS.md` if needed.
7. **History and review:** append a dated explanation of the change and its rationale to `prompts/chatgpt-conversation.md`; never rewrite old content or retroactively edit prompts already implemented/in progress. Commit the micro-step and **stop for ChatGPT review**.

## Persistent frontend invariant for all future Claude prompts

For any work that changes public HTML, templates, metrics pages, dashboards, article content or Cloudflare static publishing, explicitly apply [the question-first frontend contract](../CODING_GUIDELINES.md#public-website-question-first-frontend-contract-d086-d090) (D086/D090): **one question H1, direct answer first, then evidence**; all public metrics and dashboards are question pages. Homepage lists newest-first questions, 50/page with static pagination. Preserve the existing registry, SEO, drafts/approvals, immutable editions, verified metric provenance and staging `noindex`; use `./run.sh site-preview` and human visual review before staging deployment. Do not add a second dashboard content architecture. Distinguish unavailable measurements from verified observations.

## Before releasing the prompt / approving the result

Check every item above explicitly. After Claude finishes, inspect the actual diff/code, tests, report, four design-question files and history update before writing the next prompt. Correct earlier omissions through a small follow-up, not by rewriting historical prompt files.

## Current product direction (2026-11-03)

Finish one bounded, durable OpenAI-only LLM Metrics pipeline before live-onboarding Anthropic, Google or xAI. Metrics measures; Router (EXACT/AUTO execution) and Xchange (market/bidding) are later products. Existing Google Cloud project: `llm-metrics-513617`; never create a project automatically. Recheck current cloud pricing before provisioning rather than assuming previous estimates.
