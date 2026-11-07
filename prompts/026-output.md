# Step 026 output — Question registry and immutable dated Q&A editions

## Status: COMPLETE (local only), awaiting ChatGPT review

This step built a minimal question registry and immutable dated editions on the Step 025 `site.json`/`page.json` system. It added:
- a chronological home feed;
- a `/questions` directory;
- stable question pages with edition history;
- a redirect plan;
- `noindex` for the empty metric page;
- a second educational article (as a **draft**).

**Nothing is published:** `site_content/archive/` is empty. Hosting, DNS, cloud and Step 023 are untouched, and Step 027 has not started.

| Content | Basis |
|---|---|
| Article text | Real, from the repository's code and docs. Facts are checked by tests against `scheduled_collector`, `object_results`, `latency`, `workloads` and `targets` |
| Benchmark numbers | **None** in any article. Tests use synthetic fixtures only |
| Publication dates in tests | Synthetic (`2026-11-08…`, `2026-11-10…`) and only in temporary copies |

## Changed files

| File | Change |
|---|---|
| `llm_metrics/static_site.py` | Registry (`load_question`, `_check_registry`), `Edition`/`Question`/`Published`, `edition_route`, `load_manifest`, `plan_editions`, `plan_site`, `freeze`; pages for the home feed, directory, hub and editions; canonical/robots/redirect handling; updated checks; `--publish-at`/`--preview-at` |
| `llm_metrics/site_templates/page.html`, `base.html`, `_macros.html`, `_methodology.html` (new) | Edition header and "What changed?", edition history, earlier editions, home feed, `/questions` directory, general banner, generated methodology link |
| `llm_metrics/site_content/site.json` | Registers the `/questions` page and the second question |
| `…/questions/how-to-measure-openai-ttft/` | Now `question.json` (`q0001`) + `editions/e1/` (the Step 025 content, moved; `status: approved`; dates removed) |
| `…/questions/prevent-duplicate-paid-llm-calls/` | **New** `q0002` + `editions/e1/` (`status: draft`) |
| `…/pages/questions/` | **New** `/questions` directory page |
| `…/pages/home/intro.html` | Wording updated for the two kinds of question page |
| `…/metrics/openai-ttft/` | Methodology link is now generated (shown only when the article is published); `methodology.html` removed |
| `tests/test_site_editions.py` | **New.** 27 tests |
| `tests/test_static_site.py` | Updated to publish into a temporary content copy first |
| `README.md`, `DECISIONS.md` (D083), `PROJECT_STATUS.md`, `design-questions/026/*`, `design-questions/README.md`, `prompts/chatgpt-conversation.md` | Docs |

## Design (D083)

**Registry.** `question.json` holds:
- an opaque `question_id` (`q0001`);
- its stable `path`, `related_metrics`, `aliases` (collision-checked) and `reviewed_distinct_from`;
- `editions` in order.

Duplicate ids are refused, as are near-identical H1s (difflib ≥ 0.85) unless marked as reviewed-distinct. Distinct intents are never merged automatically.

**Editions** (`editions/eN/`):
- the Step 025 page format plus `status` (`draft`/`approved`), `summary` (feed blurb), `what_changed` (required exactly for editions after the first) and `source_commit`;
- every new edition needs a new `answer_revision`;
- **no dates in content**: `date_published`, `date_modified` and `published_at` are refused.

**Publishing:**
- `--publish-at YYYY-MM-DDTHH:MM:SSZ` takes each approved, unarchived edition (in registry order, after the previous edition's time) and assigns its route: `/reports/<UTC date>/<slug>`, then `/r2`, `/r3`.
- It builds and checks the whole site in memory, writes the edition HTML create-only to `site_content/archive/<route>/index.html`, appends to `archive/manifest.json` (`llm-metrics.publication.v1`), and replaces the output directory last.
- Each manifest entry holds: route, `question_id`, `edition_id`, `published_at`, answer/editorial revision, `answer_basis`, `dataset_sha256` (null), methodology version, edition content SHA-256, HTML SHA-256, source commit and site URL.
- A no-change re-run publishes nothing.

**Immutability:**
- Archived HTML is served byte-for-byte on every later build and never re-rendered.
- The build refuses:
  - a modified archive file;
  - edited content of a published edition;
  - unlisted archive files;
  - manifest entries without an edition;
  - another `--site-url`.
- An old edition never links to newer ones.
- An interrupted freeze (page written, manifest not) is adopted on re-run only when the bytes are identical.

**Pages:**
- **`/`:** "Published questions, newest first". Every edition appears, so a question can appear more than once.
- **`/questions`:** one entry per `question_id` with its editions.
- **Stable question page** (for example `/how-to-measure-openai-ttft`, the Step 025 canonical):
  - the latest published edition's answer, plus the current dataset findings if a dataset is supplied;
  - "First published", and "Answer updated: what changed";
  - edition history and related metric links;
  - Article `datePublished` from the first edition, `dateModified` from the latest.
- **Dated edition:**
  - "Published on (UTC)", answer revision and basis, and an "archived, never changed" note;
  - "What changed?", earlier editions, and a link to the current answer;
  - no live data;
  - canonical to the stable page; browseable and not `noindex`.
- **Breadcrumbs:** Home › Questions › question › "8 November 2026 edition". Metric pages keep Home › LLM Performance › …

**Indexing:**
- A metric page with no dataset, or a synthetic one, is `noindex`. Educational pages are indexable without any data.
- `--preview-at` renders drafts at a provisional time with a "Draft preview" banner, `noindex` on every page, and never archives.

**Redirect plan:** output `redirects.json` lists `<slug>-latest` and aliases → stable path, status 301. Rules are checked for collisions, missing targets and chains. A host-neutral plan is all that exists; Step 027 implements it on a host.

**Empirical-claim gate:**
- A methodology edition whose prose states a number with ms, tokens/s or % is refused.
- Dataset-based editions are refused until immutable metric snapshots exist.

**Second article:** "How do we prevent duplicate paid LLM API calls in scheduled benchmarks?" (`/prevent-duplicate-paid-llm-api-calls`, draft).
- **Controls described:**
  - the create-only GCS slot claim (`ifGenerationMatch=0`), read-back, the 120 s server-clock check, `duplicate_skip`, and refusal on an ambiguous claim;
  - no retries: scheduler retries 0, one HTTP request per provider call (no SDK), storage-only bounded retries, claimed slots never retried;
  - fixed scope and an exactly-96-slot, 24-hour policy; an invoke-only scheduler identity; the 7-minute late limit; expiry rechecked; storage preflight;
  - offline tests (8 concurrent runs → 1 call; minute-by-minute deliveries → exactly 96 calls).
- **"What these controls do not guarantee":**
  - owner bypass;
  - requests capped, not money, and budgets only alert;
  - the crash window;
  - slots deliberately given up;
  - clock and scheduler dependence;
  - 412 vs 403 not observed.
- Every numeric or code fact is asserted against the source by `DuplicateCallArticleTest`.

## Tests

**`tests/test_site_editions.py`, 27 tests:**
- **Default content:** nothing is published until frozen; the metric page says the methodology article isn't published; publishing takes only approved editions; the committed archive verifies.
- **Lifecycle:** two questions are published on D1, then one is republished with a materially changed answer on D2. Checked:
  - date-first routes;
  - old edition bytes are identical in the archive and the output, and the old edition has no link to the new one;
  - the home feed has 3 entries, newest first, with TTFT twice;
  - `/questions` groups both TTFT editions under one entry;
  - the stable page shows the new answer, "Answer updated", history, the metric link, and `datePublished` = D1 with `dateModified` = D2;
  - canonicals: edition → stable page, not `noindex`;
  - a no-change publish is a no-op with the manifest unchanged;
  - the redirect plan has no chains;
  - a data-only refresh creates no edition and leaves old bytes intact while the stable page's findings refresh.
- **Same day:** the second same-day edition gets `/r2`; UTC date boundary.
- **Refusals:**
  - modified archive bytes;
  - edited published content;
  - an orphaned archive file;
  - another site URL;
  - a missing `what_changed`;
  - a reused `answer_revision`;
  - a backdated or malformed publish time;
  - an unverified empirical claim;
  - similar questions without review (passes once reviewed);
  - a duplicate `question_id`;
  - an alias collision.
- **Failure handling:** a failed build keeps the previous output; an interrupted freeze is adopted only when identical.
- **Preview:** drafts shown, `noindex` and banner everywhere, nothing archived; preview combined with freeze is refused.
- **Duplicate-call article facts match the code:** 15-minute slot, 7-minute late limit, 120 s skew, 96 slots, profile and workload, `duplicate_skip`, `if_generation_match=0`, 3 storage attempts, the 8-thread and 96-call tests, scheduler `retries: 0` (checked when `gcloud.md` is present), and a limits section present.

**`tests/test_static_site.py`:** the 31 Step 025 tests were updated to the edition layout. They now also check that the metric page is `noindex` while educational pages are not, and that Article `datePublished` comes from publication.

**Validation:**
- **Docker `./run.sh test`: `Ran 622 tests`, `OK (skipped=5)`, 0 failures.** That is 595 + 27. The 24 PostgreSQL integration tests passed, the dashboard smoke test returned HTTP 200, and the 5 skips are the pre-existing container-config skips.
  - The first run had 1 error: `gcloud.md` is not copied into the test image. That check now runs only when the file exists.
- **Style:** pyink, isort and pylint are clean on `static_site.py`, `test_static_site.py`, `test_site_editions.py` and `test_web.py`, run in a `python:3.13-slim` container.
- **Editorial report on the preview:**
  - TTFT: 33% of sentences are longer than 20 words (warn).
  - Duplicate-calls article: keyphrase checks pass; 28% long sentences (warn).
  - Both: manual review of readability and intent.

## Limitations / deferred

- **Metric snapshots not implemented:**
  - no dated metric snapshots (`/reports/<date>/metrics/openai/ttft`);
  - no sample-size threshold or draft gate for metrics;
  - no release manifest of output HTML/CSS hashes;
  - no Q&A edition citing an immutable dataset.

  The prompt's "two datasets produce two metric reports" acceptance check is therefore **not met**, deliberately, to keep the step minimal for educational publishing. Dataset-based answers are refused until this exists.
- **Archive styling:** archived pages use the live `/assets/site.css`, so their bytes are frozen but their styling is not.
- **Self-canonical editions:** there is no flag or criteria yet for a genuinely distinct edition to be self-canonical; all editions canonicalize to the stable page.
- **Approval record:** "approved" is a field only; no reviewer or approval timestamp is recorded.
- **Similarity check:** a simple string ratio.
- **Hosting gaps (Step 027):** `robots.txt`, sitemap, HTTP headers, real redirects, and the trailing-slash host constraint from D082.

## Expense and cloud actions

**None.** No hosting, DNS, GCP, provider or paid action. Docker was used locally for tests and lint.

## Minimum steps to publish the reviewed educational pages on llmxchange.com

1. **Review.** ChatGPT reviews Step 026. The owner and ChatGPT review a preview of both articles:

   ```bash
   python -m llm_metrics.static_site --output /tmp/site --site-url https://llmxchange.com --preview-at 2026-11-08T09:00:00Z
   python -m http.server 8000 --bind 127.0.0.1 -d /tmp/site
   ```
2. **Approve.** Set `"status": "approved"` in `questions/prevent-duplicate-paid-llm-calls/editions/e1/page.json` in a reviewed commit. The TTFT edition is already approved.
3. **Confirm the domain.** Confirm that you control DNS for `llmxchange.com`; this hasn't been verified.
4. **Approve hosting.** Approve a bounded hosting step (Step 027). It needs:
   - a static host that serves `/slug` without a trailing-slash redirect;
   - the 301 rules from `redirects.json`;
   - `robots.txt` and a sitemap listing only the stable pages (`/`, `/questions`, `/llm-performance` and the two question pages), excluding dated editions and the `noindex` metric page;
   - CSP and `X-Content-Type-Options` headers;
   - a managed TLS certificate.

   Firebase Hosting in `llm-metrics-513617` was suggested in Step 025; pricing must be rechecked before provisioning.
5. **Publish and deploy on the same day,** so the recorded date is the real one:

   ```bash
   python -m llm_metrics.static_site --output site_build --site-url https://llmxchange.com --publish-at <UTC now>
   ```

   Commit and push `llm_metrics/site_content/archive/`, then deploy exactly `site_build/`.
6. **Verify.** Use Search Console: verify the domain, submit the sitemap, run URL Inspection on both question pages, and run the Rich Results Test.

## Recommended next step (one)

After ChatGPT review: review and approve the draft duplicate-calls article, then run the approved minimal hosting step (Step 027), so that steps 5–6 above can happen together.

## MARKETING CHECKPOINT

- **Publishable after review (educational):**
  - how we measure OpenAI TTFT;
  - how we prevent duplicate paid calls in scheduled benchmarks, stated as controls with explicit non-guarantees;
  - that answers are versioned and archived unchanged.
- **Not publishable:**
  - any measured OpenAI number, success rate or cost;
  - any ranking or "fastest" claim;
  - "guaranteed no duplicate charges";
  - any claim that the site is live or indexed.

## Design Q&A (concise)

- **Lead engineer:** *How is old HTML kept byte-identical as code changes?*
  - Answer: it is frozen create-only into the archive with SHA-256s for both HTML and source content, served verbatim, and modification, orphans or a site-URL change are refused. Archive pages are written before the manifest, and the output is swapped last.
  - Weakness: archived pages use the live CSS.
- **Principal engineer:** *Why are dates assigned at publish time, and why are editions canonical to the stable page?*
  - Answer: there is one writer of dates (the manifest), so URLs and dates are derived and cannot disagree. Canonicalizing near-duplicates consolidates signals while the archives stay browseable.
  - Weakness: no self-canonical criteria; a crude similarity check.
- **Senior manager:** *What is needed to go live?*
  - Answer: review and approve the draft, confirm DNS, run an approved hosting step, then publish and deploy the same day and verify in Search Console.
  - Risk: readers taking controls as guarantees; immutable corrections need new editions.
- **Director:** *Is versioned publishing worth the friction?*
  - Answer: yes for a credibility product. It adds no new systems and doesn't delay education.
  - Gap: metric snapshots must exist before real numbers go live.

**STOP: awaiting ChatGPT review. Step 027 not started.**
