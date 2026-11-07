# Senior manager — Step 027a: question-first site

**Step context:** Step 027a made questions the primary discovery interface of the static LLM Xchange site: a home page that lists questions newest first (50 per page, `/page/N` only when needed), optional categories, a question page that leads with the answer, metric questions that link to the existing metric evidence, four new draft articles, a simpler stylesheet, and an update of the existing workers.dev staging Worker.

---

## Question

What can a visitor see on staging now, and what still needs a human decision before the new questions appear?

## Answer

- Staging shows only approved content: the homepage, `/questions`, Metrics, Costs, the metric page and the one approved article (How do you measure OpenAI API TTFT?).
- Four new articles and the duplicate-paid-calls article are drafts. They appear only in a local `--preview-at` build. Approving one means setting `status` to `approved` after review; it then appears on the next staging build, and in production only after an explicit `--publish-at` freeze.
- The metric question says plainly that no validated measurements have been published.

## Critique

With one approved question, the new homepage looks sparse on staging; the design is only fully visible after approvals. Approval is a manual JSON edit, which is easy to get wrong without review.
