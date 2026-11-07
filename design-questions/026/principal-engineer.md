# Principal engineer — Step 026: question registry and immutable editions

**Step context:** Step 026 extended the Step 025 static site with a minimal question registry (`question.json`: opaque `question_id`, stable path, editions), immutable dated editions frozen into a committed archive (`/reports/<UTC date>/<slug>[/rN]`, manifest `llm-metrics.publication.v1`), a chronological home feed, a `/questions` directory, stable question pages with edition history, a redirect plan, `noindex` for empty metric pages, and a second article on preventing duplicate paid calls. Local only.

---

## Question

Why are publication dates kept out of the content files and assigned only at freeze time? And why does a dated edition canonicalize to the stable question page instead of to itself?

## Answer

**Dates come from publication, not content.**
- In Step 025, `date_published` lived in `page.json`. That let content claim a publication that had not happened, and editing it rewrote history.
- Now `page.json` rejects `date_published`, `date_modified` and `published_at`. The only source of truth is the manifest entry written by `--publish-at`.
- Routes are derived from it (`edition_route`: UTC date, then `/rN` by same-day count). So the URL, the visible "Published on", Article `datePublished` and the manifest cannot disagree.
- Editions must be published in registry order, at increasing times.

**Canonical to the stable page.**
- Most new editions refine one answer, so dated pages are near-duplicates of the stable page.
- Google's canonicalization guidance treats `rel=canonical` as a consolidation hint. Pointing every dated edition at `/how-to-measure-openai-ttft` concentrates signals on one URL.
- The dated pages stay crawlable and browseable: not `noindex`, and linked from the stable page and `/questions`. That avoids contradictory hints.
- The stable page's Article has `datePublished` from the first edition and `dateModified` from the latest.

**Identity stays separate from wording.** `question_id` (q0001) is opaque, so titles can change. Near-duplicate titles are refused unless they are explicitly reviewed as distinct.

## Critique

**Good:** one writer of dates, and URLs derived from facts. Duplicate-content policy is explicit, and genuinely different intents are not auto-merged.

**Weak / missing:**
- There are no documented criteria or flag for a genuinely distinct historical analysis to be self-canonical; the prompt allows that.
- The similarity check is a crude string ratio. It will miss paraphrases and can flag false positives.
- Data-backed answers are refused because there are no metric snapshots yet.

**Stronger:**
- Add a reviewed `self_canonical: true` edition flag with written criteria.
- Implement metric snapshots, so a data-backed answer edition can cite immutable evidence.
