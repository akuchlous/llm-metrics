# Lead engineer — Step 025: static question and metric pages

**Step context:** Step 025 added `llm_metrics.static_site`, a deterministic local generator (Jinja2, no Flask/SQL/GCS) that builds a home page, an `/llm-performance` hub, the Q&A article `/how-to-measure-openai-ttft` and the metric page `/metrics/openai/ttft`. Editorial text lives in reviewed `site_content/` fragments with an explicit `answer_revision`; numbers come only from a validated, canonical `llm-metrics.analytics.v1` summary declared `real` or `synthetic`, or an explicit no-data state. Pages carry canonical/OG metadata, breadcrumbs matching `BreadcrumbList` JSON-LD, `Article` JSON-LD, a meta CSP, and pass build-time checks. Nothing was hosted.

---

## Question

Untrusted strings can reach a page from two places: the analytics summary and the content files. How does the generator stop HTML injection and JSON-LD `<script>` breakout, and how do you know it works?

## Answer

**Data values:**
- Every summary value is rendered through Jinja2 with `autoescape=True` and `StrictUndefined`, so a missing view key fails the build instead of rendering empty.
- Only canonical summaries pass `load_dataset`, but string fields such as caveat `detail` are still treated as hostile. A test injects `</script><script>alert(1)</script><img onerror=…>` into a caveat, then checks that the page contains the escaped text and no `<script>alert` or `<img`.

**JSON-LD:**
- `json_ld()` serializes with `json.dumps`, then replaces `<`, `>`, `&`, U+2028 and U+2029 with `\\uXXXX` escapes. Only then is the text marked safe for the `<script type="application/ld+json">` element.
- JSON parsers decode the escapes back to the original characters. A test sets the article title to `How do </script><script>alert("x")</script> …` and checks three things: the page still has exactly two `<script` tags, the escapes are present, and the parsed `headline` equals the original title.

**Content fragments:**
- They are reviewed repository HTML inserted unescaped, so `_FragmentChecker` (stdlib `html.parser`) rejects any tag outside the allowlist, any attribute except `a[href]`, any href that is not an internal path or `https://`, and comments.
- Tests cover `<script>`, `onclick`, `javascript:`, `http:`, `<h1>`, `style` and comments.

**Defence in depth:**
- The meta CSP `default-src 'none'; style-src 'self'` blocks any script, inline style or external load that slipped through.
- `check_site` fails the build if any `<script>` is not `application/ld+json`.

## Critique

**Good:**
- Escaping is on by default, and the one place that marks text safe (`json_ld`) is small and tested.
- Fragments are validated rather than sanitized, so a bad edit fails loudly instead of being silently changed.

**Weak / missing:**
- A meta CSP cannot set `frame-ancestors`, and some hosts ignore meta policies for certain directives. Real response headers belong to the hosting step.
- The fragment allowlist is enforced by a hand-written parser, not a mature sanitizer library. That is acceptable because the input is reviewed content, but the code needs maintenance as tags are added.
- No test covers the `href` values the templates themselves build.

**Stronger:**
- Have the host send the same CSP as an HTTP header, plus `X-Content-Type-Options` and `frame-ancestors 'none'`.
- Add property-based tests that generate random strings into every summary string field.
