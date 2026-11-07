# Step 025 output — First question-driven static pages: TTFT Q&A article and metric page

## Status: COMPLETE (local only), awaiting ChatGPT review

This step built a deterministic, offline static site generator and four cross-linked pages:
- the Q&A article **"How do you measure OpenAI API time to first token (TTFT)?"** at `/how-to-measure-openai-ttft`;
- the TTFT metric page `/metrics/openai/ttft`;
- the home page `/`;
- the `/llm-performance` hub, which is the breadcrumb parent.

Nothing was hosted or deployed, and no DNS, cloud, provider or paid action was taken. **Production launch is not claimed.**

**Which content is real and which is synthetic:**

| Content | Basis |
|---|---|
| Article text, methodology and the setup table | **Real.** Written from, and tested against, the actual code (`latency.py`, `openai_provider.py`, `targets.py`, `workloads.py`, `pricing.py`) and docs |
| Every number seen in tests and previews | **Synthetic.** From the committed Step 024 fixture mirror, rendered with `--data-source synthetic`, which adds a banner and `noindex` |
| Real measurements | **None.** No real Step 023/024 dataset was mirrored or rendered |
| Default build (no `--analytics`) | Shows "No validated measurements have been published yet" on both pages |

Step 023 is untouched. Step 024 is still awaiting its own review.

## Changed files

| File | Change |
|---|---|
| `llm_metrics/static_site.py` | **New.** Content loader and validators, dataset loader and validator, view preparation, JSON-LD, rendering, build-time page checks, editorial report, output writer, CLI |
| `llm_metrics/site_templates/` | **New.** `base.html`, `page.html`, `_macros.html`, `_findings.html`, `_measurements.html`, `_setup.html`, `_provenance.html` |
| `llm_metrics/site_static/site.css` | **New.** Minimal responsive CSS with a dark-mode media query |
| `llm_metrics/site_content/` | **New.** `site.json` registry, plus a `page.json` and HTML fragments for each page |
| `tests/test_static_site.py` | **New.** 31 tests |
| `tests/test_web.py` | Import guard narrowed (see D082) |
| `README.md` | New section "Static question and metric pages (local only)" |
| `DECISIONS.md` | D082 |
| `PROJECT_STATUS.md`, `design-questions/025/*`, `design-questions/README.md`, `prompts/chatgpt-conversation.md` | Status, role files, index, history |

## Design

**Content model.** Adding an article requires no new HTML templates.
- Each page is a directory in `site_content/`. Its `page.json` holds:
  - kind and path;
  - title, H1, meta description and breadcrumb name;
  - for questions: focus keyphrase, slug terms, `editorial_revision`, `answer_revision`, `answer_basis`, and `date_published`/`date_modified`/`authors` (only when known);
  - the ordered sections.
- Each section is either a reviewed static HTML fragment or a named generated section.
- A future article is a new directory plus one line in `site.json`. The shared template supplies metadata, breadcrumbs, JSON-LD and checks.

**Editorial text and data are kept apart.**
- Fragments are static HTML, not templates, so dataset values cannot reach them.
- Numbers appear only in the generated sections:
  - `findings`: a compact view on the Q&A page;
  - `measurements`: the full view on the metric page;
  - `setup`: read from code;
  - `provenance`.
- A test renders the site with and without data and asserts that the answer, method and limitations sections are byte-identical.

**Answer interface (for Step 026).**
- The page shows "Answer revision" (`how-to-measure-openai-ttft/answer-r1`) and "Answer based on". The basis is `methodology` today: the answer was not reviewed against data. A `dataset` basis must name the reviewed dataset's SHA-256.
- The page shows "Published", or "Not yet published (draft)" while unset.
- A separate line, "Data last refreshed: latest measurement …", is the only thing a data refresh changes.

**Dataset gate.**
- Only the exact canonical bytes from `record_analytics` are accepted.
- Checked before rendering:
  - schema `llm-metrics.analytics.v1`;
  - population equal to the metric page's `expected_population` (prod, openai, gpt-6-luna, `openai.gpt-6-luna.v1`, `interactive-chat-v1`, gcp/us-central1);
  - reliability and category counts;
  - metric units and null-iff-zero-count;
  - every success has a TTFT;
  - evidence count and manifest hash;
  - caveats.
- The caller must declare `--data-source real|synthetic`.
- A content-addressed copy is published at `/data/analytics/<sha256>.json` and linked from the provenance table.

**Metric page.**
- What TTFT measures (editorial).
- Data window and latest-measurement time.
- A "Preliminary" notice built from the summary's caveat codes.
- Cards: TTFT p50/p95, n, observed success rate.
- A static SVG bar chart of TTFT min, p50, p95 and max, using width attributes and no inline styles, so it works under the CSP. Bar lengths are proportional to the table values.
- Tables:
  - latency and throughput, success-only;
  - reliability, including failures by category;
  - slot completeness, when supplied (otherwise a sentence says it is not);
  - tokens and estimated cost, with unknown values shown as "unknown".
- The dataset's caveats, the setup table from code, provenance, and a link to the methodology article.
- A test checks that it does not repeat the article.

**Q&A article.** Sections in order:
1. **Short answer.** Defines TTFT and our client-side boundary.
2. **What our measurements show.** Generated, or the no-data notice, plus the link "Explore measured OpenAI TTFT".
3. **How the measurement works.**
   - `time.perf_counter()` starts just before the streaming request, so DNS, TCP/TLS, upload, queueing and prefill are included.
   - It stops at the first `response.output_text.delta` event.
   - First byte, first content chunk and first token are distinguished. Only the first content chunk is measured, with no token-level precision claimed.
   - The workload: fixed Lumen Notes offline-sync prompt, a hash pinned by a test, at most 300 output tokens, `reasoning.effort=none`, `store=false`, explicit cache mode with no breakpoints, all under profile `openai.gpt-6-luna.v1`.
   - Collection: one request per 15-minute slot from Cloud Run us-central1, no retries, immutable records, no stored prompts, responses or raw errors.
   - Summarisation: offline, nearest-rank percentiles.
4. **Exact measurement setup.** A table generated from code, including the prompt SHA-256, list prices and the methodology version.
5. **Limitations.**
6. **Related pages**, including the source code on GitHub.

**SEO and structured data** (checked against Google Search Central on 2026-11-07: AI features, breadcrumbs, Article, canonicalization):
- **Basic HTML:** `lang=en`, UTF-8, viewport, and a unique title, meta description and H1 per page.
- **Canonical URLs:** an absolute https canonical from a validated `--site-url` (https, lowercase host, no port, path, query or fragment). `og:title`, `og:description` and `og:url` match. There is no `og:image`, because no image exists.
- **Breadcrumbs:** visible `nav aria-label="Breadcrumb"` with Home › LLM Performance › page. The `BreadcrumbList` items and URLs are identical to it. Every page has at least two items except the home page, which has none.
- **Structured data:**
  - `Article` (headline, description, url, mainEntityOfPage, inLanguage), with dates and authors only when set. No publisher is asserted.
  - `WebPage`, `CollectionPage` or `WebSite` for the other pages.
  - No AI-specific markup and no `llms.txt`, per Google's statement that no special markup is needed.
- **Escaping and CSP:**
  - JSON-LD escapes `<`, `>`, `&`, U+2028 and U+2029.
  - A meta CSP: `default-src 'none'; style-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'`. The only `<script>` elements are JSON-LD.
- **Readable without JavaScript:** facts are in HTML text and tables with captions and units, so the pages need no JavaScript.

**Build-time checks** fail the build, and nothing is written:
- the `<head>` facts above and title uniqueness;
- one leading H1 and no skipped heading levels;
- breadcrumbs matching JSON-LD, with positions 1..n and the last item equal to the canonical;
- `Article` URL and headline;
- every internal link resolving to a generated file, external links https only;
- no executable script;
- question → metric and metric → methodology links.

**Yoast-inspired editorial report** (advisory). Current result for the article:
- **Pass:**
  - keyphrase "time to first token" in title, H1, meta description and introduction;
  - slug terms;
  - title length 50, meta description 159;
  - subheadings;
  - density 0.7%;
  - no paragraph over 150 words;
  - 4 internal links, plus an outbound source link.
- **Warn:** 36% of sentences are longer than 20 words (Yoast suggests no more than 25%). Left for editorial review rather than rewritten to satisfy a heuristic.
- **Manual:** readability and intent; Rich Results Test once hosted.

These scores do not establish SEO success.

**Output.** `write_site` builds in a sibling temp directory and moves it into place. It replaces only a previous build (marker file `.llm-metrics-site`) and refuses other existing directories and paths inside the package. Builds are byte-identical across runs; no build time is written anywhere.

## Decisions

**D082** (full text in `DECISIONS.md`):
- the generator and content model;
- the answer interface;
- the dataset gate and `real`/`synthetic` labelling;
- SEO and CSP choices;
- `METHODOLOGY_VERSION = "llm-metrics.ttft-methodology.v1"`, with what it pins;
- the hosting constraint below.

It also amends the D056 import guard: `jinja2`/`markupsafe` are now also allowed in `static_site.py`. Flask/Werkzeug remain `web.py`-only, and every other module stays free of all four.

## Evidence and tests

**`tests/test_static_site.py`, 31 tests:**
- **No-data build:** page set; no-data state with no ms values, no chart, no noindex; deterministic render.
- **Head metadata:** lang, charset, viewport, canonical, OG, one H1, CSP, unique titles.
- **Breadcrumbs:** visible trail equals `BreadcrumbList`, and every crumb exists.
- **Article:** no invented dates, authors, publisher or image; "Not yet published (draft)".
- **Links and structure:** cross-link anchor text; all internal links resolve; JSON-LD the only script; no inline styles; answer-first H2 order.
- **Methodology vs code:**
  - the setup table equals the code (profile, 300-token cap, cache policy, settings, prompt SHA-256 equal to `test_workloads.PROMPT_SHA256`);
  - the article prose names the facts the code defines, and the code really contains `"response.output_text.delta"` and `time.perf_counter()`.
- **Datasets (synthetic):**
  - values with units, provenance hashes, failure category, slot table and the exact JSON copy;
  - "Preliminary" and "p95 equals the maximum" visible;
  - banner and `noindex` on every page when synthetic, none when real;
  - a data refresh leaves the answer, method and limitations byte-identical;
  - records-only datasets show the "slot completeness not supplied" sentence;
  - a failures-only dataset shows "unknown", never `0 ms`, and no chart.
- **Dataset refusals:**
  - empty, malformed, non-canonical, NaN or duplicate-key input;
  - wrong schema, another region, inconsistent counts, a TTFT count different from the successes, an evidence mismatch, negative values;
  - an unknown source label or a symlink.
- **Escaping:**
  - an XSS payload in a dataset caveat is escaped;
  - a `</script>` title cannot break out of JSON-LD, and the headline round-trips;
  - unsafe fragments are refused: `<script>`, `onclick`, `javascript:`, `http:`, `<h1>`, `style`, comments;
  - a broken internal link (`/metrics/openai/total-latency`, which does not exist) is refused.
- **Answer metadata:**
  - known dates and authors render, both visibly and in JSON-LD;
  - invalid metadata is refused: dataset basis without a SHA, unknown basis, non-ISO date, modified without published, empty author, unsafe revision id;
  - a dataset basis names its dataset.
- **Configuration and output:**
  - site URL validation (http, path, port, query, uppercase, userinfo, empty);
  - rebuilds are byte-identical and replace only a previous build;
  - output inside the package is refused.
- **CLI:** exit 0 with a report; 2 when `--data-source` is missing; 1 with nothing written for invalid data. The editorial report statuses are pass, warn or manual.

**Local preview:** `python -m http.server` served all four routes and the stylesheet with HTTP 200. For directories it first redirects `/slug` to `/slug/` (see Limitations).

**Validation:**
- Focused tests: `tests.test_static_site` and `tests.test_record_analytics`, 62 OK. `tests.test_web` 28 OK after the guard change.
- **Full Docker `./run.sh test`:**
  - The first run found exactly one failure: the D056 import guard flagged `static_site.py`. That led to the D082 amendment.
  - **Rerun after the fix: `Ran 595 tests`, `OK (skipped=5)`, 0 failures.** That is 564 + 31. The 24 PostgreSQL integration tests passed, the dashboard smoke test returned HTTP 200, and the 5 skips are the pre-existing container-config skips.
- **Style:** `pyink --check`, `isort --profile google --check-only` and `pylint --rcfile=.pylintrc --disable=inconsistent-quotes` are clean on `static_site.py` and `test_static_site.py`, run in a `python:3.13-slim` container.

**Deferred to the live website:** Rich Results Test, Search Console URL Inspection, sitemap and `robots.txt`, mobile performance (Core Web Vitals), HTTP security headers, real-host redirect behaviour.

## Limitations

- **No real data has been rendered.** Every number seen so far is synthetic.
- **Trailing slash:** canonicals are `/how-to-measure-openai-ttft` with no slash, and directory-based static servers redirect `/slug` to `/slug/`. The production host must serve clean URLs without that redirect, or the URL policy must change in a reviewed step.
- **Hosting pieces not built:** `robots.txt`, sitemap, HTTP security headers, dated versions, aliases and redirects (Steps 026/027). A meta CSP cannot set `frame-ancestors`.
- **Thin metric page:** it is indexable even in its no-data state, which may be thin content until real data exists. A per-page `noindex` switch is not implemented.
- **Attribution and dates:** no author, publisher or organization is asserted, and `date_published` is unset.
- **Fragment validation:** it uses a hand-written allowlist parser rather than a sanitizer library. That is acceptable for reviewed repository content.
- **Mobile layout:** checked by design (viewport, responsive CSS, scrollable tables), not with a browser or Lighthouse.

## Expense and cloud actions

**None.** No hosting, DNS, GCP or provider calls. Docker was used locally for tests and lint, and a localhost `http.server` for preview.

## Shortest safe path to making the first article public on llmxchange.com

The educational article doesn't need any measurement data. Each step below needs the review or approval noted, and nothing here has been done.

1. **Review (ChatGPT plus the user).** Review Step 025 and the article text: accuracy of the timer description, tone, and the open sentence-length warning. Decide the metric page's state: publish it with the honest no-data notice, or keep it `noindex` until real data exists (a small follow-up).
2. **Decide publication order.** Approve publishing the educational, no-data build before Step 026's versioning, or do 026 first. This is a process decision for ChatGPT review; I have not changed the sequence.
3. **Confirm the domain.** Confirm that you control DNS for `llmxchange.com`. This hasn't been verified.
4. **Run one approved, bounded hosting step** (a minimal Step 027). The recommended option, to be priced again before provisioning, is **Firebase Hosting in the existing project `llm-metrics-513617`**:
   - `firebase.json` with `cleanUrls: true` and `trailingSlash: false`, matching the canonicals;
   - HTTP headers for the CSP and `X-Content-Type-Options`;
   - a managed TLS certificate for the custom domain;
   - minimal `robots.txt` and `sitemap.xml` listing only the canonical URLs.

   No new servers or databases are needed, and expected cost at this traffic is within the free tier, but that must be re-verified. GitHub Pages is an alternative, but its handling of extensionless URLs for directories differs and would need checking.
5. **Publish.** Set `date_published` in the article's `page.json` as a reviewed commit. Build with no dataset and deploy that exact build.
6. **Verify live.** Run the Rich Results Test, Search Console verification and URL Inspection, and submit the sitemap.

## Recommended next step (one)

After ChatGPT review, decide the publication order under the "publish educational content early" priority. Specifically, either approve a bounded hosting step for the reviewed no-data build (path above) before Step 026, or confirm that Step 026 comes first.

## MARKETING CHECKPOINT

- **Publishable educational claims, after editorial review:**
  - how we measure OpenAI API TTFT on the client: first text chunk, not first byte or exact first token;
  - the fixed, versioned workload and request settings;
  - that failures are recorded and never shown as fast requests;
  - nearest-rank percentiles;
  - immutable, hash-listed evidence;
  - the open-source code.
- **Not publishable:**
  - any OpenAI TTFT, latency, reliability or cost number (no real dataset has been rendered or reviewed);
  - any ranking, "fastest" or provider-uptime claim;
  - any suggestion that structured data guarantees rich results or AI Overview placement;
  - any statement that the site is live.

## Design Q&A (concise)

- **Lead engineer:** *How are injection and JSON-LD breakout prevented?*
  - Answer: Jinja2 autoescape and `StrictUndefined` for data; `json_ld()` escapes `< > & U+2028 U+2029`; editorial fragments go through an allowlist validator; a meta CSP with nothing executable; and a build check that only JSON-LD scripts exist. Each is tested with attack strings.
  - Weakness: a meta CSP is limited, and real headers come with hosting.
- **Principal engineer:** *How is "a data refresh never rewrites the answer" structural?*
  - Answer: fragments are static HTML with no data access, data appears only in named generated sections, the answer revision and basis are explicit inputs, and a byte-identity test compares builds with and without data. A content-addressed dataset copy and a pure `render_site` prepare for 026.
  - Weakness: a hard-coded number in prose can still go stale.
- **Senior manager:** *What is ready and what is missing for going live?*
  - Answer: the article and the no-data metric page are ready locally. Still needed: editorial review, domain confirmation, approved hosting with clean URLs, `robots.txt` and sitemap, and setting `date_published`. No numbers or rankings may be claimed.
- **Director:** *Is question-first static publishing the right strategy?*
  - Answer: yes. It matches how people search and Google's "no special AI markup" guidance, costs almost nothing, and keeps the provenance story.
  - Risks: single-model misreading, thin metric pages, process speed versus review, and no named author or organization yet.

Full role files: `design-questions/025/`.

**STOP: awaiting ChatGPT review. Steps 026 and 027 not started.**
