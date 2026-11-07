# Director — Step 027: Cloudflare-ready static site

**Step context:** Step 027 made the static site Cloudflare-ready offline: a redesigned "LLM Xchange" look and top navigation, `/costs` built from a private reviewed cost ledger (`cost_ledger.py`), `sitemap.xml`/`robots.txt`/`_redirects`/`_headers`/`404.html`, a `wrangler.jsonc` for Workers Static Assets with `drop-trailing-slash`, a host-routing emulator, a forbidden-content scan, and `publish_runner` with independent editorial and metrics lanes. Nothing was deployed.

---

## Question

The site publishes the project's own actual costs next to its benchmark methodology. Is radical cost transparency a sound strategic choice for LLM Xchange, and how does the architecture keep it credible as the project grows (more providers, an API, weekly updates)?

## Answer

**Why transparency fits:**
- The product's value is trust in independent measurement. Showing what the benchmark itself costs, and refusing to show a total until it is reconciled, demonstrates the same discipline readers should expect from the numbers.
- It also answers a real audience question: what it costs to run an LLM benchmark.

**How the architecture keeps it credible:**
- **One hostname and static files on Cloudflare:** near-zero fixed cost, nothing always-on.
- **Independent lanes:** editorial answers (reviewed, immutable editions), metrics (cadenced, gated on complete real data) and costs (operator-reviewed ledger). A failure in one never alters another.
- **A future Flask `/api/*`** can sit behind the same hostname through a separately approved route. It would read only a validated summary, never raw records.
- **Growth path:** the next step (028) adds immutable metric snapshots and thresholds before any real result goes public.

## Critique

**Good:**
- The strategy and the architecture reinforce each other.
- Low fixed cost keeps the experiment sustainable.
- There is no tracking, consistent with a trust brand.

**Weak / missing:**
- Transparency invites scrutiny of every gap. "Lifetime total not yet verified" will be visible for a while.
- There is no audience or traffic plan yet.
- No named author or publisher.

**Stronger:** decide named authorship and a short public roadmap page, so visible gaps read as deliberate progress rather than unfinished work.
