# Step 018f — Lead engineer

**Step context:** Step 018f fixes the Docker build-context bug (`.dockerignore` excluded `scripts/` without a negation for the installer), upgrades Mako to 1.3.12 for two CVEs, adds offline `test_container_config.py` to prevent the regression, and documents a full GCP authorization checkpoint — stopping before any billable cloud action.

**Question:** `.dockerignore` now has two lines for `scripts/`: first `scripts/` (exclude), then `!scripts/install_requirements.py` (re-include). What would have happened if the negation line came first? Why must these appear in this order, and what test now catches a regression?

## Answer

Docker evaluates `.dockerignore` rules top-to-bottom; the last matching rule for a path wins. If `!scripts/install_requirements.py` appeared before `scripts/`, the sequence would be: (1) re-include `scripts/install_requirements.py` — matches, excluded=False; (2) exclude `scripts/` — matches, excluded=True. The negation would be silently overridden and the installer would be absent from the build context. The `docker build` command would succeed (the `COPY` step silently copies nothing if the glob matches zero files), but `python scripts/install_requirements.py` would then fail with `No such file or directory` — a confusing runtime error rather than a build-time error.

The fix places the exclusion first, then the negation immediately after it. `test_container_config.py` implements a simplified version of Docker's matching rules — exact name, directory prefix, and simple globs — and asserts that none of the Dockerfile's `COPY` source paths are definitively excluded by `.dockerignore`. It also asserts `scripts/install_requirements.py` specifically passes. A `@unittest.skipUnless` guard makes the class skip gracefully when `Dockerfile` and `.dockerignore` are absent (e.g. inside the `test_end_to_end_in_a_copy` temporary copy).

## Critique

- **Good:** The test catches the exact regression that caused the bug — a COPY source excluded by .dockerignore — without requiring a Docker daemon.
- **Weak:** The `.dockerignore` matching implementation in the test is a simplified approximation. It handles exact paths, directory prefixes, and single-segment `*` wildcards, but not `**` (recursive glob), `?`, or character classes. A future pattern like `*.py` in `.dockerignore` could exclude `scripts/install_requirements.py` without the test catching it.
- **Improve:** Consider asserting that the negation rule (`!scripts/install_requirements.py`) appears strictly after the exclusion rule (`scripts/`) in the file, as a belt-and-suspenders order guard. Additionally, `fnmatch.fnmatchcase` or the `pathspec` library implements the full Docker pattern spec more reliably than a hand-rolled matcher.
