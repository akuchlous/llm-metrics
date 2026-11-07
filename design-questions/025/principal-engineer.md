# Principal engineer — Step 025: static question and metric pages

**Step context:** Step 025 added `llm_metrics.static_site`, a deterministic local generator (Jinja2, no Flask/SQL/GCS) that builds a home page, an `/llm-performance` hub, the Q&A article `/how-to-measure-openai-ttft` and the metric page `/metrics/openai/ttft`. Editorial text lives in reviewed `site_content/` fragments with an explicit `answer_revision`; numbers come only from a validated, canonical `llm-metrics.analytics.v1` summary declared `real` or `synthetic`, or an explicit no-data state. Pages carry canonical/OG metadata, breadcrumbs matching `BreadcrumbList` JSON-LD, `Article` JSON-LD, a meta CSP, and pass build-time checks. Nothing was hosted.

---

## Question

The prompt requires that a data refresh never silently rewrite an editorial conclusion. How does the design make that a structural property rather than a convention, and how does it prepare for Step 026's versioned answers?

## Answer

**Structural separation:**
- Editorial text is static HTML in `site_content/questions/how-to-measure-openai-ttft/*.html`. Fragments are **not** Jinja templates, so they have no access to the dataset.
- Data enters a page only through named generated sections (`findings`, `measurements`, `setup`, `provenance`). `_load_page` rejects any other generated name per page kind.
- The test `test_data_refresh_never_changes_the_answer` renders the site with and without a dataset and asserts that the `answer`, `method` and `limitations` sections are byte-identical.

**Explicit answer identity:**
- `page.json` carries `answer_revision` (`how-to-measure-openai-ttft/answer-r1`), `editorial_revision`, and `answer_basis`.
- `answer_basis` is either `methodology` (reviewed against no data, which is true today) or `dataset` plus the reviewed dataset's SHA-256, which is mandatory and validated.
- The page shows "Answer revision", "Answer based on" and "Published". Separately, inside findings, it shows "Data last refreshed: latest measurement …". A new p50 can change only the second.

**Provenance chain for 026:**
- Every data-bearing page shows the methodology version, the analytics schema, the dataset SHA-256 and the record-manifest SHA-256.
- A content-addressed copy, `/data/analytics/<sha256>.json`, is emitted. A dated snapshot can cite exactly the bytes it was built from.
- `render_site()` is pure (config, dataset, content directory → `{path: bytes}`), so 026 can stage, compare and promote outputs without re-implementing rendering.

## Critique

**Good:**
- The guarantee is enforced by the type of content (static fragments) and by a test, not by reviewer discipline.
- Answer identity is an input, never inferred from numbers.

**Weak / missing:**
- Nothing stops a reviewer from writing a hard-coded number into a fragment. The prose is static, so that number would go stale silently.
- The site-level registry is a flat list. Relationships such as question → metric are single fields, enough for one pair but not a graph.
- `page.json` has no schema version of its own.

**Stronger:**
- Add a lint that flags digits followed by units ("ms", "%") in fragments for manual review.
- Version the content metadata format before 026 adds answer history to it.
