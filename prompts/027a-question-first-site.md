# Step 027a — Question-first LLM Xchange site (small follow-up to Step 027)

**One micro-step.** Simplify the existing Step 027 static site so that questions are the primary discovery interface. Builds on Step 027 (`prompts/027-output.md`, D084, D085) and the deployed staging Worker. Do not reopen or rewrite Step 025–027 prompts.

## Scope
1. **Homepage = questions only**, newest first: the question as clickable title, a one-line summary, the publication/update date only when it is a real (archived) publication, and an optional category (Performance, Cost, Reliability, Engineering). 50 questions per page; `/` then `/page/2`, `/page/3`… as static HTML with self-canonical URLs and working previous/next links. Never generate an empty page.
2. **Question pages:** "Question" label and H1, then a direct **Answer** first, then optional Explanation, Methodology, Verified data (when available), Limitations, Related questions. Remove dashboard-like clutter.
3. **Metrics are questions too:** metric questions (e.g. "What is OpenAI's time to first token (TTFT)?") link to the existing metric evidence and say "No validated measurements have been published yet" until a validated dataset exists. Never invent numbers. Preserve metric routes and data contracts.
4. **New educational drafts:** TTFT vs total response time; output token count and response time; why identical requests have different latency; plus the OpenAI TTFT metric question. All stay `draft` under the existing approval and immutable-publication workflow. The duplicate-paid-calls draft stays a draft.
5. **Design:** minimal, typographic, fast, light/dark, accessible; no hero graphics or homepage dashboard.
6. Keep `/questions`, `/costs`, article and metric URLs working.

## Deployment (authorized for this step only)
Update the existing free staging Worker `llmxchange` at `https://llmxchange.akuchlous.workers.dev` after tests and safety checks, with `--staging` (approved answers only, no dated editions, `noindex, nofollow`). No domain purchase, production deploy, DNS, GCP, Step 023, paid services, Flask API or scheduled publishing.

## Validation and artifacts
Focused tests, full Docker suite, public-file safety scan, Wrangler dry-run, live route checks. Design questions under `design-questions/027a/` (four roles), `prompts/027a-output.md`, `PROJECT_STATUS.md`, `DECISIONS.md`, history note in `prompts/chatgpt-conversation.md`. Commit, push, **STOP for ChatGPT review**.
