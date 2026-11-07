# Senior manager — Step 025: static question and metric pages

**Step context:** Step 025 added `llm_metrics.static_site`, a deterministic local generator (Jinja2, no Flask/SQL/GCS) that builds a home page, an `/llm-performance` hub, the Q&A article `/how-to-measure-openai-ttft` and the metric page `/metrics/openai/ttft`. Editorial text lives in reviewed `site_content/` fragments with an explicit `answer_revision`; numbers come only from a validated, canonical `llm-metrics.analytics.v1` summary declared `real` or `synthetic`, or an explicit no-data state. Pages carry canonical/OG metadata, breadcrumbs matching `BreadcrumbList` JSON-LD, `Article` JSON-LD, a meta CSP, and pass build-time checks. Nothing was hosted.

---

## Question

We want the first educational article live on llmxchange.com quickly. What exactly is ready, what is missing before it can be public, and what must we avoid claiming?

## Answer

**Ready locally:**
- The TTFT article. It answers first, then explains the timer boundaries from the real code, the fixed Lumen Notes workload, the request settings and the limitations.
- The metric page, which shows an honest "no validated measurements have been published yet" state.
- The home and hub pages, with breadcrumbs, canonical URLs and structured data.
- All of these build in one offline command, with 31 tests, and need no dataset. Education can ship before the benchmark pilot is analysed.

**Missing before public:**
1. ChatGPT and human review of the article text, which is the editorial gate. The build report has one advisory warning: 36% of sentences have more than 20 words.
2. Confirming control of the llmxchange.com DNS. Ownership hasn't been checked.
3. An approved hosting step: a host that serves clean URLs without a trailing-slash redirect, plus `robots.txt`, a sitemap and HTTP security headers.
4. Setting `date_published` only when it actually goes live.

**Must not claim:**
- Any OpenAI number. No real dataset has been rendered; test builds use synthetic data, which is bannered and `noindex`.
- Rankings, "fastest" or provider uptime.
- That structured data guarantees rich results or AI Overview inclusion.

## Critique

**Good:** educational value is decoupled from data readiness, and the honest no-data state means a page can go live without waiting for numbers. The editorial report makes SEO hygiene reviewable rather than a vibe.

**Weak / missing:**
- A metric page with no data is thin content. It might be better kept `noindex` until a real dataset exists, and that switch isn't implemented.
- The step sequence (026 versioning, then 027 hosting) delays publication. Changing the order is a process decision for review.

**Stronger:** propose an explicit "educational-only first publication" policy: the article and hub are indexable, the metric page is `noindex` until real data exists. This would be a small, reviewed change.
