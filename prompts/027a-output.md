# Step 027a output — Question-first LLM Xchange site

## Status: COMPLETE; staging updated; awaiting ChatGPT review. Production not started.

**Staging URL:** https://llmxchange.akuchlous.workers.dev (temporary, `noindex, nofollow`). Worker `llmxchange`, version a46f81ef-0b13-4de1-8b5e-0464d29817bb (previous: 34fc2545-0f58-4b06-abbf-7d6e1f3a25a9).

## What changed
- **Home page = questions only** (`static_site._question_listing`): one row per published question, newest first by latest edition time. Each row shows the question (link to its stable page), a one-line summary, an optional category tag, and "Published"/"Updated" only for real archived publications outside previews.
- **Pagination:** `QUESTIONS_PER_PAGE = 50`; `/` is page 1, `/page/N` exists only when needed (no empty pages, no `/page/1`). Each page is self-canonical, has visible previous/next links (`rel="prev"`/`rel="next"`), passes the same link and SEO checks, and joins the sitemap when indexable. `WebSite` structured data only on `/`.
- **Categories:** optional `question.json` `category` ∈ Performance, Cost, Reliability, Engineering (validated). `/questions` groups questions by category, A to Z.
- **Question page layout:** "Question" label + H1, category/date line, **Answer** first, then the content's sections, auto-generated **Related questions** (same category first), and a compact **About this answer** (revision, basis, archived editions). The old edition-history, card and "Explore" clutter is gone.
- **Metric question** `/openai-ttft` ("What is OpenAI's time to first token (TTFT)?") uses the existing generated findings section: it says "No validated measurements have been published yet" and links to `/metrics/openai/ttft`. Metric routes and data contracts are unchanged.
- **New drafts** (status `draft`, not approved, not on staging): `/ttft-vs-total-response-time`, `/output-tokens-and-llm-response-time`, `/why-llm-latency-varies`, `/openai-ttft`. The duplicate-paid-calls article stays a draft.
- **Design:** new single-column typographic stylesheet (serif headings, system fonts, hairline-separated question list, light/dark, under 20 KB, no JavaScript). Nav: Questions, Metrics, Costs. Home H1 "LLM Xchange" with the requested tagline.
- Existing URLs preserved: `/questions`, `/costs`, `/llm-performance`, `/how-to-measure-openai-ttft`, `/metrics/openai/ttft`, the `-latest` redirect.

## Decisions
- D086: question-first discovery supersedes the Step 027 "chronological edition feed" home page; editions, archive and canonicals unchanged.

## Tests and checks
- Focused: 120 site tests OK (7 new in `tests/test_site_questions.py`: listing, pagination with patched page size, category directory, page layout, metric question has no numbers, drafts absent from staging and no preview dates, unknown category refused).
- Full Docker `./run.sh test`: 656 tests, OK (6 skipped, as before). Lint (pyink, isort, pylint) clean.
- Staging build: 7 pages; drafts absent (grep); every HTML page `noindex, nofollow`; forbidden-content scan clean; archive unchanged (no `site_content/archive/`); `wrangler deploy --dry-run` passed, no bindings.
- Live: `/`, `/questions`, `/llm-performance`, `/metrics/openai/ttft`, `/costs`, `/how-to-measure-openai-ttft` 200; trailing slash and `/index.html` 307; `-latest` 301; drafts, `/page/2`, `/reports/...`, unknown paths and `/_headers` 404; CSP, nosniff, Referrer-Policy, Permissions-Policy and `X-Robots-Tag: noindex, nofollow` present; `robots.txt` has no sitemap line; sitemap empty. Live pages and CSS byte-identical to the build.

## Limitations
- Staging shows one question until more are approved; the new drafts can be seen only in a local `--preview-at` build.
- No screenshots, Lighthouse or axe: the headless-browser container was not permitted in earlier attempts and was not retried. Visual review in a browser is still needed.
- Preview/staging question pages still carry the preview time as `datePublished` in structured data (pages are `noindex`).
- `/.llm-metrics-site` and `/redirects.json` are still served (not sensitive).

## Expense and cloud actions
One update of the existing free, assets-only staging Worker. No domain, DNS, production, GCP, Step 023, paid service, Flask API or scheduler. No paid API calls.

## Recommended next step (one)
Review the four drafts (and the duplicate-calls draft) in a local preview and approve the ones that are ready, then rebuild staging.

## MARKETING CHECKPOINT
- **Publishable after approval (educational):** the TTFT methodology article and, once approved, the four new explanations.
- **Not publishable yet:** any measured TTFT or other benchmark number, rankings, cost totals, "the site is live".

## Design Q&A (concise)
- **Lead engineer:** pagination never creates empty pages; tested with a patched page size.
- **Principal engineer:** editions and archive unchanged; dates appear only for real publications.
- **Senior manager:** staging shows approved content only; drafts need a manual approval.
- **Director:** question-first suits search and trust; value still depends on Step 028 data.

Full files: `design-questions/027a/`.

## Follow-up: "Which LLM API metrics are useful, and why?" (2026-11-07)

- New question q0007 at `/useful-llm-api-metrics` (category Performance), **approved at the owner's request** for the static pages. It explains TTFT, total response time, output tokens per second, reliability, token usage and cost per request, how to summarize them (percentiles, failures counted separately, sample size and window), what our benchmark records, and limitations. No measured values; it links to `/metrics/openai/ttft`, `/costs` and the TTFT methodology article.
- Not frozen: no dated edition was created (that needs `--publish-at`, Approval B).
- Tests: focused 120 OK; full Docker 656 OK (6 skipped); lint clean. Editorial report: all checks pass.
- Staging Worker updated to version 7e8681e8-1ae2-453b-af1e-44acbe5c6f9b: home lists two questions; `/useful-llm-api-metrics` 200, trailing slash 307, `-latest` 301, `noindex, nofollow`, byte-identical to the build; drafts still 404.

**STOP: awaiting ChatGPT review. Approval B and Step 028 not started.**
