# Director — Step 025: static question and metric pages

**Step context:** Step 025 added `llm_metrics.static_site`, a deterministic local generator (Jinja2, no Flask/SQL/GCS) that builds a home page, an `/llm-performance` hub, the Q&A article `/how-to-measure-openai-ttft` and the metric page `/metrics/openai/ttft`. Editorial text lives in reviewed `site_content/` fragments with an explicit `answer_revision`; numbers come only from a validated, canonical `llm-metrics.analytics.v1` summary declared `real` or `synthetic`, or an explicit no-data state. Pages carry canonical/OG metadata, breadcrumbs matching `BreadcrumbList` JSON-LD, `Article` JSON-LD, a meta CSP, and pass build-time checks. Nothing was hosted.

---

## Question

The website strategy is question-first, educational content plus evidence pages, on static hosting. Is this the right way to build an audience and credibility for llmxchange.com, and what are the strategic risks?

## Answer

**Why question-first fits:**
- People search for questions ("how do you measure OpenAI TTFT?"), not for dashboards.
- An article that answers directly and explains the method from real, open-source code gives value now, with one model and no data. It also earns trust that a bare number from one model, one workload and one region could not.
- Google's own guidance for AI Overviews and AI Mode is ordinary helpful content plus technical SEO, with no special markup. That is what was built: crawlable text, tables, breadcrumbs and accurate structured data.

**Why separate metric pages:**
- Numbers will change on a cadence. Conclusions should change only on review.
- Separate URLs let `/metrics/openai/ttft` refresh without republishing the article. They also give each metric a stable, linkable home as more providers are added.

**Why static:**
- Hosting costs are near zero at this scale, against a project target of ≤ $10/day.
- There is no server to attack or keep up.
- It matches D069 (static HTML plus versioned JSON).
- It reuses the provenance chain: the dataset hash and manifest are on the page, and the JSON is downloadable.

**Strategic risks:**
1. A single-model site invites misreading as a ranking. Every page states its scope.
2. Thin or empty metric pages could look unfinished.
3. Publication velocity versus the review process. The current sequence puts versioning (026) before hosting (027).
4. Brand and attribution: no author, publisher or organization identity is asserted yet. That limits E-E-A-T signals until real people or an organization are named.

## Critique

**Good:** the strategy stays credible by construction (no invented claims, visible provenance) while letting educational content ship early.

**Weak / missing:**
- There is no audience or traffic plan: no Search Console, no sitemap, no distribution.
- There is no named author or organization.
- The roadmap order is not yet re-decided under the new "publish early" priority.

**Stronger:** make a decision record on publication order (educational-first hosting before full versioning, or not) and on who the named author or publisher is. Then measure whether the article gets impressions before investing in more metric pages.
