# Lead engineer — Step 026: question registry and immutable editions

**Step context:** Step 026 extended the Step 025 static site with a minimal question registry (`question.json`: opaque `question_id`, stable path, editions), immutable dated editions frozen into a committed archive (`/reports/<UTC date>/<slug>[/rN]`, manifest `llm-metrics.publication.v1`), a chronological home feed, a `/questions` directory, stable question pages with edition history, a redirect plan, `noindex` for empty metric pages, and a second article on preventing duplicate paid calls. Local only.

---

## Question

"Published historical HTML must never be modified." Templates, CSS and code will keep changing. How does the build guarantee an old edition's bytes stay identical, and what breaks loudly if someone tries to change one?

## Answer

**The guarantee comes from not re-rendering.**
- `--publish-at` renders each approved, unarchived edition once and writes the HTML create-only (`open(path, "xb")`) into `site_content/archive/reports/…/index.html`.
- It then appends a manifest entry with the HTML SHA-256 and the SHA-256 of the edition's source directory.
- Every later build copies archived bytes verbatim (`Published.frozen`). A template change therefore cannot alter history.

**`plan_editions` refuses** when:
- an archived file's hash differs from the manifest ("was modified");
- an edition's source fragments or `page.json` changed after publication ("add a new edition instead");
- a file in the archive is not listed;
- a manifest entry has no edition;
- the `--site-url` differs from the one baked into the archived canonicals.

**Ordering protects against interruption.** The whole site is built and checked in memory first. Archive pages are written before the manifest, and the output directory is swapped last.
- A crash between steps leaves unlisted archive pages. A re-run of the same freeze adopts them only if they are byte-identical (tested).
- A failed build leaves the previous output untouched (tested).

**Archived pages still get one check:** `check_site` verifies their internal links still resolve. Deleting a page an old edition links to fails the build.

## Critique

**Good:** immutability is enforced by storage and hashes, not by convention. Every refusal path has a test.

**Weak / missing:**
- Archived pages reference the live `/assets/site.css`. Their *appearance* can change even though their bytes don't.
- Git history is the only protection against someone editing both the archive file and its manifest hash. That edit would be visible in review but not refused by the build.
- `os.replace` on the manifest is atomic, but there is no fsync.

**Stronger:**
- Freeze a content-addressed copy of the CSS for each edition.
- Add a CI check that `site_content/archive/` is append-only relative to `main`.
