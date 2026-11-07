# Principal engineer — Step 027a: question-first site

**Step context:** Step 027a made questions the primary discovery interface of the static LLM Xchange site: a home page that lists questions newest first (50 per page, `/page/N` only when needed), optional categories, a question page that leads with the answer, metric questions that link to the existing metric evidence, four new draft articles, a simpler stylesheet, and an update of the existing workers.dev staging Worker.

---

## Question

The home page used to be a chronological feed of dated editions (Step 026/027). Does listing questions instead weaken the immutable-edition model or the "no unverified dates" rule?

## Answer

- Editions are unchanged: `plan_editions`, the archive manifest and verbatim serving of frozen bytes are untouched. Dated editions are still reachable from each question's "About this answer" section, and remain canonical to the stable page (D083).
- The home page and `/questions` now link only to stable question pages, which removes near-duplicate links from the main discovery surfaces.
- Dates are shown only when real: a row or question page shows "Published"/"Updated" only when its latest edition has a dated `/reports/` route **and** the build is not a preview. Draft previews and staging builds therefore show no publication date (tested).
- Metric questions use the existing generated `findings` section and `unavailable` macro, so they cannot render numbers without a validated dataset; a test asserts no millisecond or percentage value appears.

## Critique

This reverses part of the Step 027 prompt ("the homepage is a chronological publication feed, not a unique-question list") at the user's request; D086 records it. Structured data still carries `datePublished` from the preview time on staging pages, which are `noindex, nofollow`; a later step could omit it in previews.
