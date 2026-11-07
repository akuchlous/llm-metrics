# Senior manager — Step 026: question registry and immutable editions

**Step context:** Step 026 extended the Step 025 static site with a minimal question registry (`question.json`: opaque `question_id`, stable path, editions), immutable dated editions frozen into a committed archive (`/reports/<UTC date>/<slug>[/rN]`, manifest `llm-metrics.publication.v1`), a chronological home feed, a `/questions` directory, stable question pages with edition history, a redirect plan, `noindex` for empty metric pages, and a second article on preventing duplicate paid calls. Local only.

---

## Question

What exactly has to happen, and who has to approve it, for the two educational articles to go live on llmxchange.com? What risks remain once they are public?

## Answer

**Current state:**
- The TTFT article edition is `approved`, because it was reviewed in Step 025.
- The new duplicate-paid-calls article is `draft`.
- Nothing is published, so the archive is empty.
- The default build is safe to share: home, `/questions`, `/llm-performance` and a `noindex` metric page saying that no measurements are published.

**To go live:**
1. **Review the drafts.** ChatGPT and the owner review a `--preview-at` build (noindex, bannered). The duplicate-calls article is then approved by setting `status: approved` in a reviewed commit.
2. **Publish.** Run `--publish-at <actual UTC time>` once, and commit `site_content/archive/`.
3. **Host.** An approved hosting step (Step 027) deploys the built output. It needs clean URLs with no trailing slash, the 301 redirects from `redirects.json`, `robots.txt`, a sitemap and security headers.
4. **Verify.** Use Search Console.

**Remaining risks:**
- The duplicate-calls article states controls carefully, including a "What these controls do not guarantee" section. Readers may still read it as a guarantee.
- An empty metric page could look unfinished. It is now `noindex`, so it won't be indexed, but users can still reach it.
- Once published, an edition cannot be edited. Corrections become new editions with a stated "what changed", which is intentional but slower.

## Critique

**Good:**
- Publication is a single, deliberate, reversible-before-commit command.
- Drafts can't leak into indexable output.
- Education ships without any benchmark data.

**Weak / missing:**
- There is no named author or publisher, which weakens credibility signals.
- "Approved" is just a field in a file, with no recorded approver or approval date.

**Stronger:** record the reviewer and the approval commit in the manifest entry. Name the author once that is decided.
