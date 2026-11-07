# Step 027 output — Cloudflare-ready static llmxchange.com, costs ledger and release lanes (offline)

## Status: COMPLETE OFFLINE, awaiting ChatGPT review. Approvals A and B not requested yet; nothing deployed.

## Decisions recorded from the Step 026 review

- **Step 026** is accepted as complete for the educational Q&A scope. Its prompt was not rewritten.
- **Moved to Step 027 (done here):** the top-level `/costs` page, pricing Q&A foundations and the private cost-ledger input format. Estimates are never published as charges; incomplete billing shows "Full lifetime total not yet verified."
- **Moved to Step 028:** immutable dated metric snapshots, sample-size publication thresholds and the weekly metrics Q&A workflow. These are **mandatory before any real benchmark result is published.**
- **Step 023** untouched.

## What was built

| Area | Change |
|---|---|
| **Design** | "LLM Xchange" brand mark; top navigation (Questions → `/questions`, Metrics → `/llm-performance`, Project Costs → `/costs`, Methodology → the TTFT question once it is published); skip link; cards for the chronological feed, the `/questions` directory and explore links; responsive grid; readable 44rem measure; tabular numbers; dark mode; visible focus states; reduced-motion handling; system fonts only. The stylesheet is under 20 KB; no JavaScript, web fonts, images or trackers. |
| **`/costs`** | New `costs` page kind: an answer-first explanation plus a generated charges section from `llm_metrics/cost_ledger.py`. Without a ledger it says "No verified billing data has been published yet" and is `noindex`. |
| **Cost ledger** | Private `llm-metrics.cost-ledger.v1` → public `llm-metrics.cost-summary.v1`. Rules below. |
| **Hosting files** | Every build writes `sitemap.xml`, `robots.txt`, `_redirects` (from `redirects.json`), `_headers` and `404.html`. |
| **Cloudflare config** | `wrangler.jsonc`: assets only (no `main`), `html_handling: "drop-trailing-slash"`, `not_found_handling: "404-page"`, `directory: ./site_build`. Not deployed. |
| **Host emulation** | `static_site.resolve()` reproduces Cloudflare's documented routing for offline tests and link crawls. |
| **Forbidden-content scan** | `scan_public()` runs on every public file; any hit fails the build. |
| **Release lanes** | `llm_metrics/publish_runner.py` and `site_content/publishing.json`. |
| Pricing Q&A foundations | The `/costs` stable page and the ledger contract. No candidate pricing article was written: their answers need real bills or forecasts that don't exist yet, so writing them now would invent figures. |

**Cost-ledger rules:**
- Amounts are decimal strings, kept per currency with no FX conversion.
- Only `charged` entries count, net of refunds. `invoiced_unpaid` is shown separately. `estimate` is never added.
- A source without bills is unknown (not $0).
- A lifetime total is shown only when every declared source is fully reconciled through the cut-off with nothing unpaid.
- Overlapping charged periods, reused evidence hashes and duplicate ids are refused.
- `private_reference` values are never output and are added to the forbidden-content scan.

**Hosting files:**
- **`sitemap.xml`:** only indexable canonical pages. It never lists dated editions (canonical to their question), aliases, drafts, preview builds or `noindex` pages (the empty metric page, `/costs` without a ledger). `lastmod` is given only from real publication times, and a rebuild never advances it.
- **`robots.txt`:** allow all, with a sitemap reference.
- **`_headers`:** CSP plus `frame-ancestors 'none'`, `nosniff`, referrer policy and permissions policy.
- **`404.html`:** `noindex`, no canonical.

**Host emulation:**
- `/slug` → 200.
- `/slug/` and `/slug/index.html` → 307 to `/slug`.
- `_redirects` → 301.
- Underscore files and unknown paths → 404 page.

**Forbidden-content scan** rejects:
- `gs://`, the results bucket name, `storage.googleapis.com`, `OPENAI_API_KEY`, `private_reference`, synthetic request ids;
- `sk-…` and `req_…` patterns;
- the ledger's private references.

**Release lanes:**
- **Editorial:** publishes approved editions at an explicit `--publish-at`. It needs no analytics or GCP, and reuses the last *accepted* metrics dataset (hash-checked) so metric pages never regress.
- **Metrics:** refreshes only when all of these hold:
  - a scheduled slot is due;
  - the dataset is `real`;
  - it changed;
  - its window ended before the current UTC day;
  - it is not a partial day, unless `--allow-preliminary` is given as an explicit approval.
- **Isolation:** a failed metrics run changes nothing, and editorial releases still work.
- **Controls:** `--dry-run`; the `publishing_enabled` emergency switch; `history.jsonl`. Cadence is `daily` | `every_3_days` | `weekly` at 02:00 UTC.

**Hosting comparison** (official docs read 2026-11-07):

| Option | Cost model | Slashless URLs | 404 | Decision |
|---|---|---|---|---|
| **Cloudflare Workers Static Assets (Free)** | "Requests to static assets are free and unlimited"; no storage charge; 20,000 files per version; 25 MiB per file | `drop-trailing-slash`: `/folder` → 200; `/folder/` and `/folder/index.html` → 307 to `/folder` | `404-page` | **Chosen** |
| Cloudflare Pages (Free) | free static; 500 builds/month; 20,000 files | redirects `/about/index.html` → `/about/` (trailing slash), so it conflicts with our canonicals | assumes an SPA without `404.html` | Alternative only |
| Firebase Hosting | 10 GB storage, 360 MB/day free, then $0.15/GB | configurable | yes | Fallback (overage exposure) |

**Open items for staging:**
- Workers documents the `_redirects` (2,000 static) and `_headers` (100 rules) *limits*, but the pages read don't document their syntax or status codes. Both must be verified on staging.
- The Free plan's "100,000 requests/day" line is ambiguous for asset-only traffic. Confirm it on staging.

**Future `/api/*` (not built):** Flask could later serve `https://llmxchange.com/api/v1/...` from a private origin via a separately approved Cloudflare route, with everything else static.
- Benefits: same-origin, so no CORS; cacheable responses.
- Constraints: it must read a validated summary, never raw GCS records; routing to a Worker would be billable; it needs auth and rate limits.
- It needs its own numbered step.

## Tests

**`tests/test_site_hosting.py`, 25 new tests:**
- **Ledger:**
  - a partial ledger gives per-currency subtotals with refunds deducted, the estimate excluded, "not yet verified" and the unverified list;
  - a lifetime total appears only when everything is reconciled, and an unpaid invoice blocks it;
  - a source without bills is unknown, unless explicitly reconciled;
  - refusals: overlap, reused evidence, duplicate id, negative amount, bad currency, unknown source, refunds above the charge, period before the project start, wrong schema.
- **`/costs`:**
  - no ledger: honest notice, `noindex`, not in the sitemap;
  - a partial ledger renders "Full lifetime total not yet verified." with USD and EUR kept separate, is indexable and appears in the sitemap;
  - a private reference never appears in any public file, and content that contains one is refused.
- **Staging:** a preview for a `workers.dev` hostname is `noindex` everywhere, sends `X-Robots-Tag: noindex, nofollow`, has an empty sitemap and no sitemap line in `robots.txt`, uses canonicals on the preview host only, and archives nothing. Production builds have no `X-Robots-Tag`.
- **Hosting:**
  - the sitemap lists exactly the indexable canonical pages, with truthful `lastmod`, no editions, aliases or `noindex` metric page, and is stable across rebuilds;
  - `robots.txt`, `_headers` (CSP + `frame-ancestors`), `_redirects`, and a `404.html` that is noindex without a canonical;
  - route emulation (10 route classes); every href on every page resolves to 200 through the emulation;
  - navigation, skip link, focus and dark-mode CSS, no external CSS, under 20 KB;
  - the forbidden-content scan;
  - `wrangler.jsonc` keys (this test is skipped inside the test image, which doesn't contain that file).
- **Schedule:** daily boundaries at 01:59:59/02:00; `every_3_days` anchored; weekly on Mondays; invalid configs.
- **Runner:**
  - editorial with no dataset publishes, then reports no change;
  - the metrics gates: synthetic data refused, partial day refused, `--allow-preliminary` publishes, not due, unchanged dataset, history lines;
  - a failed metrics run leaves the output intact while an editorial release succeeds and keeps the accepted metrics;
  - a window running into the current UTC day is refused;
  - the emergency switch and dry run write nothing;
  - a tampered accepted dataset is refused.

**Existing Step 025/026 tests** were updated for the new files (costs, sitemap, 404, headers, redirects) and for `#content` anchors.

**Validation:**
- **Docker `./run.sh test`: `Ran 647 tests`, `OK (skipped=6)`, 0 failures.**
  - That is 622 + 25.
  - 6 skips: the 5 pre-existing container-config skips, plus the `wrangler.jsonc` check, which runs and passes outside the image.
  - The 24 PostgreSQL integration tests passed; the dashboard smoke test returned HTTP 200.
  - The first run had 1 error because `wrangler.jsonc` is not in the test image; that test now skips there.
- **Style:** pyink, isort and pylint are clean on the six new and changed Python files, run in a `python:3.13-slim` container.

**Not done:**
- **Screenshots and visual QA.** No local browser exists, and running a third-party headless-Chrome Docker image was not permitted in this session. Visual review and Lighthouse/Core Web Vitals are deferred to the Approval A staging deploy, or you can review a local preview.
- **Accessibility audit with tooling** (axe or Lighthouse). The basics (landmarks, skip link, focus states, captions, contrast-minded palette) are built in, but not measured.

## Limitations

- The host behaviour is emulated from the docs, not observed. `_redirects`/`_headers` syntax and the trailing-slash 307 must be confirmed on staging.
- No dated cost editions (`/reports/YYYY-MM-DD/project-costs`) and no candidate pricing articles yet. Both need real billing evidence.
- No metric snapshots or thresholds (Step 028).
- Nothing is scheduled. `publish_runner` is a local CLI.
- The ledger's completeness depends on the operator declaring every paid source.
- No named author or publisher.

## Expense and cloud actions

**None.** No Cloudflare account access, DNS change, GCP change, deploy, provider call or scheduled job. Docker was used locally for tests and lint only.

**Expected recurring cost after launch** (not verified charges):
- Workers static assets: $0 per the docs.
- Domain renewal: unknown, and to be recorded in the ledger when billed.
- No publishing job yet.

## Approvals needed next (exact plan)

**Approval A: staging on a free Cloudflare hostname.** `llmxchange.com` has **not** been purchased, and none is needed for staging. You would provide or confirm a Cloudflare account and either run the deploy yourself or approve a scoped API token. Then:
1. Build a preview for the generated hostname. It is `noindex` on every page, adds an `X-Robots-Tag: noindex, nofollow` header, has an empty sitemap and no sitemap line in `robots.txt`, and freezes nothing into the archive:
   ```bash
   python -m llm_metrics.static_site --output site_build --site-url https://<worker>.<account>.workers.dev --preview-at <UTC now>
   ```
   Real editions are not frozen with a throwaway or unowned URL.
2. Deploy with `npx wrangler deploy` (assets only).
3. Curl each route class against the `resolve()` table: slashless, slash, `index.html`, a dated edition, the `-latest` 301, the 404, headers and `sitemap.xml`. Run the forbidden-content scan on the deployed files.
4. Take desktop and mobile screenshots and run Lighthouse.
5. Teardown is `npx wrangler delete`; rollback is a redeploy of the previous build.

Expected cost: $0 for asset-only Workers on the Free plan, per the docs. Re-verify at execution time.

**Approval B: production.**
1. You buy `llmxchange.com` (or confirm you control it) and put its DNS on Cloudflare; this is a separate decision and purchase.
2. Approve the draft duplicate-calls article.
3. Run `publish_runner editorial --publish-at <UTC now>`, then commit and push `site_content/archive/`.
4. Deploy and attach the custom domain.
5. In Search Console: verify the domain, submit the sitemap, run URL Inspection, and run the Rich Results Test.

Scheduled publishing remains off until Step 028.

## Recommended next step (one)

After ChatGPT review: request **Approval A**, the Cloudflare `workers.dev` staging deploy with live route, header and visual verification.

## MARKETING CHECKPOINT

- **Publishable after review (educational):**
  - the TTFT methodology article;
  - the duplicate-paid-call controls article (once approved);
  - the `/costs` method, and its "no verified billing data yet" status.
- **Not publishable:**
  - any benchmark number, ranking or "fastest" claim;
  - any project cost total, until bills are reconciled;
  - "$0 hosting" stated as a fact about actual spend;
  - any statement that the site is live.

## Design Q&A (concise)

- **Lead engineer:** *How do slashless URLs resolve on the host?*
  - Answer: Workers `drop-trailing-slash` matches the canonicals. `resolve()` emulates it, and every link is crawled through it.
  - Weakness: emulated, not observed; `_redirects` syntax is unverified.
- **Principal engineer:** *How does the ledger prevent estimate-as-actual and double counting?*
  - Answer: only charged entries count, per currency; overlap, reused evidence and duplicate ids are refused; a lifetime total needs full reconciliation; private references are scanned out.
- **Senior manager:** *What will it cost, and what must be approved?*
  - Answer: about $0 per the docs, plus a domain renewal. Approval A covers staging verification and screenshots; Approval B covers DNS, publishing and Search Console.
- **Director:** *Is cost transparency strategic?*
  - Answer: yes for a trust product. Independent lanes keep it credible.
  - Risks: visible gaps, no audience plan, no named author.

## Approval A: staging deployment (executed 2026-11-07)

**Public staging URL:** https://llmxchange.akuchlous.workers.dev (temporary; `noindex, nofollow`).

**Source changes:** a `--staging` build mode (D085): approved answers only, no dated editions, nothing archived, `noindex, nofollow` on every page including 404; `wrangler.jsonc` gains `workers_dev: true` and `preview_urls: false`.

**Before deploy:** Docker `./run.sh test` ran 649 tests, OK (6 skipped). The build passed the generator's link and forbidden-content checks, plus a grep scan for keys, GCP project/bucket names, account ids, emails and private ledger fields: no hits. The one "synthetic" match is the article describing the synthetic benchmark prompt. `wrangler deploy --dry-run` passed with no bindings. `git status` showed no archive changes.

**Commands run:**
```bash
python -m llm_metrics.static_site --output site_build \
  --site-url https://llmxchange.akuchlous.workers.dev \
  --preview-at <UTC now> --staging        # in the app Docker image, --network none
npx wrangler@4.152.0 deploy --dry-run
npx wrangler@4.152.0 deploy
```

**Actual resource configuration (read back from the Cloudflare API):**
- One Worker `llmxchange`, assets only (`has_assets: true`, no modules, no bindings), compatibility date 2026-11-07, version 34fc2545-0f58-4b06-abbf-7d6e1f3a25a9 at 100%.
- workers.dev enabled, preview URLs disabled; no custom domains, no routes, no DNS changes.
- 12 assets uploaded (`_headers`/`_redirects` are host config, not served).
- No paid plan or service was added. The OAuth token cannot read billing, so the plan tier was not read back via API; the account is the owner's Free account.

**Live verification:**

| Request | Result |
|---|---|
| `/`, `/questions`, `/llm-performance`, `/metrics/openai/ttft`, `/costs`, `/how-to-measure-openai-ttft` | 200 |
| `/questions/`, `/how-to-measure-openai-ttft/`, `/questions/index.html`, `/costs/index.html`, `/index.html` | 307 to the slashless URL |
| `/how-to-measure-openai-ttft-latest` | 301 to the stable page |
| `/nope`, `/prevent-duplicate-paid-llm-api-calls` (draft), `/reports/2026-11-07/...` | 404 with the site's 404 page |
| `/_headers`, `/_redirects` | 404 (not exposed) |
| `robots.txt` | `Allow: /`, no sitemap line; `sitemap.xml` has no URLs |

- Security headers present on 200, 307 and 404 responses: CSP, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`, `X-Robots-Tag: noindex, nofollow`.
- Every live page and the stylesheet are byte-identical to the build. The metric page says "No validated measurements have been published yet." and contains no millisecond values. `/costs` says "No verified billing data has been published yet." No private billing record exists or was used.
- Static accessibility checks on every live page: `lang`, viewport, `<main>`, one `h1`, skip link (not on 404), no images without alt text, dark-mode and width media queries.

**Issues:**
- The first request to `/questions/index.html` returned a plain-text 404 during propagation; repeated requests return 307.
- `/.llm-metrics-site` (the build marker, text "llm-metrics static site build") and `/redirects.json` (the public redirect plan) are served. Neither is sensitive; they can be excluded later with an `.assetsignore`.
- Desktop/mobile screenshots, Lighthouse and axe were **not run**: the local headless-Chrome container was denied by the session's permission classifier. Visual review is still needed in a browser.
- The workers.dev hostname contains the account's subdomain `akuchlous`.

**Rollback:** `npx wrangler@4.152.0 deployments list`, then `npx wrangler@4.152.0 rollback <version-id>`; full removal: `npx wrangler@4.152.0 delete --name llmxchange`.

**STOP: staging deployed and verified; awaiting ChatGPT review. Production (Approval B) and Step 028 not started.**
