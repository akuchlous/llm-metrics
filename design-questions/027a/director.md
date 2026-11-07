# Director — Step 027a: question-first site

**Step context:** Step 027a made questions the primary discovery interface of the static LLM Xchange site: a home page that lists questions newest first (50 per page, `/page/N` only when needed), optional categories, a question page that leads with the answer, metric questions that link to the existing metric evidence, four new draft articles, a simpler stylesheet, and an update of the existing workers.dev staging Worker.

---

## Question

Is a question-first site the right product shape for LLM Xchange before any real measurement is published?

## Answer

- Yes for discovery and search: each question is one stable, focused URL that answers first, which suits how people search ("why is my LLM slow?").
- It keeps the trust rules: no invented numbers, dates only for real publications, drafts held back, staging not indexed.
- It folds metrics into the same shape ("What is OpenAI's TTFT?"), so the future Step 028 data can appear as answers rather than a dashboard.

## Critique

Educational answers alone will not differentiate the site; the value depends on Step 028 publishing validated measurements. Category labels are editorial and could drift without a guideline.
