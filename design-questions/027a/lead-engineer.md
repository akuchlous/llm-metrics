# Lead engineer — Step 027a: question-first site

**Step context:** Step 027a made questions the primary discovery interface of the static LLM Xchange site: a home page that lists questions newest first (50 per page, `/page/N` only when needed), optional categories, a question page that leads with the answer, metric questions that link to the existing metric evidence, four new draft articles, a simpler stylesheet, and an update of the existing workers.dev staging Worker.

---

## Question

How does pagination avoid empty pages and keep canonical URLs and previous/next links correct, and how is that tested when the site has only a handful of questions?

## Answer

- `_question_listing()` builds one row per published question (its stable path, never a dated edition), sorted newest first by the latest edition time, with `question_id` as a deterministic tie-break.
- `_page_count()` is `max(1, ceil(n / QUESTIONS_PER_PAGE))`, so `/` always exists and `/page/N` is generated only for N ≤ count. `/page/1` is never generated; `/` is page 1.
- Each extra page is a copy of the home `Page` with its own path, so it goes through the same render loop and `check_site`: self-canonical URL, one H1, link crawl, and it joins the sitemap when indexable. `WebSite` structured data is emitted only for `/`.
- `_pager()` yields `rel="prev"`/`rel="next"` links only where a neighbouring page exists.
- `tests/test_site_questions.py` patches `QUESTIONS_PER_PAGE` to 4 against the six-question test copy: page 1 has 4, page 2 has 2, no overlap, no `/page/3` or `/page/1`, correct canonical and links, and `/page/2` in the sitemap.

## Critique

The patched page size proves the logic, not behaviour at real scale (50). Ordering by latest edition time means an answer revision moves a question to the top; that is intended ("Updated" is shown) but should be confirmed by review. Search engines no longer use `rel=prev/next` as an indexing signal; the visible links are what matter for crawling.
