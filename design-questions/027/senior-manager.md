# Senior manager — Step 027: Cloudflare-ready static site

**Step context:** Step 027 made the static site Cloudflare-ready offline: a redesigned "LLM Xchange" look and top navigation, `/costs` built from a private reviewed cost ledger (`cost_ledger.py`), `sitemap.xml`/`robots.txt`/`_redirects`/`_headers`/`404.html`, a `wrangler.jsonc` for Workers Static Assets with `drop-trailing-slash`, a host-routing emulator, a forbidden-content scan, and `publish_runner` with independent editorial and metrics lanes. Nothing was deployed.

---

## Question

What will running llmxchange.com cost, what has to be approved before it goes live, and what could still go wrong on launch day?

## Answer

**Expected hosting cost:**
- Workers Static Assets, assets only, is documented as free and unlimited for asset requests, with no storage charge and a limit of 20,000 files per version. The site is about 20 files.
- There is no Worker script, so there are no per-request charges.
- The real recurring costs are the domain renewal (amount unknown; not checked) and any later GCP publishing job (Step 028).
- None of this is a verified charge. Actual amounts go into the private cost ledger once billed.

**Approvals needed, each separately:**
1. **Approval A.** A Cloudflare account and an API token (or a manual `wrangler deploy` by you) to a non-production `*.workers.dev` staging name. Then:
   - verify the slash/redirect/404 behaviour and headers with curl;
   - take screenshots;
   - run the forbidden-content scan on the deployed files.
2. **Approval B.** Attach `llmxchange.com` (DNS on Cloudflare; ownership is unconfirmed), publish the approved editions with `--publish-at`, deploy, then verify in Search Console. Scheduled publishing stays off until Step 028.

**Launch-day risks:**
- `_redirects`/`_headers` behaving differently on Workers than documented for Pages.
- Search Console needing DNS verification.
- The duplicate-calls article being read as a guarantee.
- No screenshots yet: the offline review had no browser.

## Critique

**Good:** cost is near zero by design, and every live action sits behind a named approval. Educational content is not blocked by missing data or bills.

**Weak / missing:**
- There is no measured Lighthouse or Core Web Vitals score.
- There is no visual sign-off yet.
- The 100,000 requests/day Free-plan line is ambiguous for static assets.

**Stronger:** make screenshots and a Lighthouse run part of Approval A's checklist, and confirm the request-limit interpretation with Cloudflare's docs on staging.
