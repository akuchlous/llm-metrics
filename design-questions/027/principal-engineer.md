# Principal engineer — Step 027: Cloudflare-ready static site

**Step context:** Step 027 made the static site Cloudflare-ready offline: a redesigned "LLM Xchange" look and top navigation, `/costs` built from a private reviewed cost ledger (`cost_ledger.py`), `sitemap.xml`/`robots.txt`/`_redirects`/`_headers`/`404.html`, a `wrangler.jsonc` for Workers Static Assets with `drop-trailing-slash`, a host-routing emulator, a forbidden-content scan, and `publish_runner` with independent editorial and metrics lanes. Nothing was deployed.

---

## Question

The site must never present an estimate as an actual project cost. How does the cost ledger enforce "actual charges only", avoid double counting, and decide when a lifetime total may be shown?

## Answer

**Private input, public summary.** The operator writes `llm-metrics.cost-ledger.v1` by hand from authorized bills, so there is no billing API or credential.
- Each entry has: source, period, currency, `charged_amount` (a decimal string, after credits and including tax), refunds, `status` (`charged` | `invoiced_unpaid` | `estimate`), an evidence description and SHA-256, a last-verified time, and an optional `private_reference`.
- `summarize()` emits `llm-metrics.cost-summary.v1` without private references.
- `build()` also adds every `private_reference` to the forbidden-content scan of the public files.

**Counting rules:**
- Only `charged` entries count (net of refunds), per currency, with no FX conversion.
- `invoiced_unpaid` is shown separately.
- `estimate` is never added to anything, because a bill already contains that usage.

**Double counting is refused at validation:**
- duplicate entry ids;
- a reused evidence hash (the same invoice entered twice);
- overlapping charged periods for the same source and currency.

**Lifetime total.** It is shown only when every declared source is `fully_reconciled` with `reconciled_through` at or after the cut-off, has only charged entries, and nothing is unpaid. Otherwise the page states "Full lifetime total not yet verified." and lists the unverified sources.
- A source with no bills is "no billing records", never /bin/bash, unless it is explicitly reconciled.
- Without a ledger, `/costs` says so and is `noindex`.

## Critique

**Good:** the rules are conservative by construction, and every rule has a refusal test. Privacy is enforced twice: by omission from the summary and by the output scan.

**Weak / missing:**
- Completeness of the source list depends on the operator declaring every vendor; the code cannot know about an undeclared bill.
- There are no dated cost editions yet.
- Partial-period overlaps across different currencies of the same vendor are allowed.

**Stronger:**
- Add immutable dated cost editions with "what changed".
- Require each source's `coverage_start` to be on or before the project start before it can count as reconciled.
