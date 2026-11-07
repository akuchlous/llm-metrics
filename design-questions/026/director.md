# Director — Step 026: question registry and immutable editions

**Step context:** Step 026 extended the Step 025 static site with a minimal question registry (`question.json`: opaque `question_id`, stable path, editions), immutable dated editions frozen into a committed archive (`/reports/<UTC date>/<slug>[/rN]`, manifest `llm-metrics.publication.v1`), a chronological home feed, a `/questions` directory, stable question pages with edition history, a redirect plan, `noindex` for empty metric pages, and a second article on preventing duplicate paid calls. Local only.

---

## Question

The site now treats answers as versioned, dated publications rather than editable web pages. Is that worth the operational friction, and does it fit the goal of publishing quickly?

## Answer

**Why it is worth it:**
- The product is credibility about LLM performance, and answers will change as providers are added and data accumulates.
- If "which model is fastest?" changes next month, readers and search engines should see the current reviewed answer at the stable URL. The old answer should stay at its dated URL, unchanged, with a "What changed?" trail.
- That is the difference between a benchmark you can cite and a blog post that silently changes.

**Cost of the mechanism:**
- It is file-based, with a manifest and a create-only archive committed in git.
- No CMS, database or new dependency was added; it reuses the Step 025 templates, checks and content format.
- Hosting cost is unchanged, still static files.

**Speed:**
- Educational Q&A publishes with no analytics, GCS or collector involvement.
- The remaining steps to go live are editorial review, one publish command, and an approved hosting step.

**Scope kept small on purpose:** dated metric snapshots, sample-size thresholds and a full release manifest were deferred. They matter when numbers are published, which is not yet.

## Critique

**Good:**
- The approach matches the long-term trust strategy without slowing the first publication.
- The no-data, noindex metric page avoids thin indexed content.

**Weak / missing:**
- The prompt's metric-snapshot acceptance criterion (two datasets producing two immutable metric reports) is deferred. This must be planned before any real number goes live.
- There is no traffic or audience plan.
- Publication still depends on manual commits.

**Stronger:** before the first real dataset is published, schedule the metric-snapshot step and decide named authorship.
