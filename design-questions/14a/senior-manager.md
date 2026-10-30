# Step 14a — Senior manager

**Step context:** Step 014a moved the dashboard's HTTP boundary from `http.server` to a small Flask application (`llm_metrics/web.py`, `create_app()` factory), keeping routes, query validation, page HTML, and statuses unchanged. `dashboard.py` became an HTTP-free application/view layer, and only `web.py` imports Flask. Flask is the first runtime dependency: pinned with sha256 hashes in `requirements.txt` and installed by `run.sh` through a standard-library installer that brings a hash-verified pip zipapp when the venv has none.

**Question:** The project avoided dependencies on purpose. What changed, what risk does Flask add, and how is that risk controlled for the team?

## Answer

What changed is the goal. LLM Metrics is heading toward a public product, and a hand-written `http.server` handler doesn't scale to more pages, an API, and templates. Flask is small, well known, and keeps the HTTP code thin. The exception is narrow: one module uses it, and nothing that measures or stores data depends on it.

The new risks are supply chain, reproducibility, and onboarding. They're controlled like this:

- **Exact versions and hashes:** every package, including transitive ones, is pinned with sha256 hashes for every published file. pip runs with `--require-hashes --only-binary=:all: --isolated`, so a substituted or changed package fails to install, nothing is compiled, and local pip configuration can't change the result.
- **Release age:** every version was at least two weeks old when chosen.
- **Chromebooks without `python3-venv`:** the installer brings pip's official zipapp at a pinned version and verifies its hash before running it. No sudo, and no change to the one-command `./run.sh`.
- **Network:** only the first run and dependency updates need it, tracked by a stamp. Tests stay offline.

## Critique

- **Good:** The dependency footprint is minimal and auditable, onboarding is still one command, and a fresh-checkout run was verified for real.
- **Weak:** There's no tool to regenerate hashes. Updating a version means editing 163 lines by hand from PyPI data, which is error-prone and easy to postpone, so security updates may lag.
- **Improve:** Add a small, documented script (or adopt `pip-tools` as a development-only tool) to regenerate `requirements.txt`. Put a dependency review on the release checklist and watch the advisories for these 7 packages.
