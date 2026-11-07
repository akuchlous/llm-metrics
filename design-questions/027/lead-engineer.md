# Lead engineer — Step 027: Cloudflare-ready static site

**Step context:** Step 027 made the static site Cloudflare-ready offline: a redesigned "LLM Xchange" look and top navigation, `/costs` built from a private reviewed cost ledger (`cost_ledger.py`), `sitemap.xml`/`robots.txt`/`_redirects`/`_headers`/`404.html`, a `wrangler.jsonc` for Workers Static Assets with `drop-trailing-slash`, a host-routing emulator, a forbidden-content scan, and `publish_runner` with independent editorial and metrics lanes. Nothing was deployed.

---

## Question

The canonical URLs have no trailing slash, but the files are `slug/index.html`. How did you make sure that every URL the site emits resolves correctly on the chosen host, without deploying anything?

## Answer

**Pick a host mode that matches the URL design.** Cloudflare's HTML-handling table for `drop-trailing-slash`, folder case, is:
- `/folder` → 200 from `folder/index.html`
- `/folder/` → 307 to `/folder`
- `/folder/index.html` → 307 to `/folder`

That is exactly the slashless canonical policy from Steps 025/026, so no URL had to change. `wrangler.jsonc` sets it with `not_found_handling: "404-page"` and has no `main` script, so no request invokes a billable Worker.

**Emulate the host offline.** `static_site.resolve(files, path)` implements those rules plus `_redirects` and the 404 page. The tests check:
- slashless and slash forms;
- `/index.html`;
- dated editions;
- the `-latest` 301;
- CSS and the sitemap;
- `/_headers` and unknown paths → 404.

`test_every_link_resolves_through_the_host_emulation` crawls every href on every page through the emulator and requires a 200.

**Consistency.** Canonical, `og:url`, breadcrumbs, the sitemap `<loc>` and `_redirects` targets all use the same slashless absolute URLs.

## Critique

**Good:** the URL decision is backed by the vendor's documented table, and every internal link is crawled through it.

**Weak / missing:**
- The emulator is my reading of the docs, not Cloudflare itself.
- The `_redirects` and `_headers` syntax for Workers is not documented in the pages read; only their limits are. Both must be verified on staging.
- The trailing-slash redirect is a 307, not a 301. That is acceptable with canonicals, but should be noted.

**Stronger:** run `wrangler dev` locally (needs Node and approval to install it) or a staging deploy (Approval A), then curl each route class and diff the results against `resolve()`.
