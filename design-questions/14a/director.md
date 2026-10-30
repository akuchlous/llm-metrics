# Step 14a — Director

**Step context:** Step 014a moved the dashboard's HTTP boundary from `http.server` to a small Flask application (`llm_metrics/web.py`, `create_app()` factory), keeping routes, query validation, page HTML, and statuses unchanged. `dashboard.py` became an HTTP-free application/view layer, and only `web.py` imports Flask. Flask is the first runtime dependency: pinned with sha256 hashes in `requirements.txt` and installed by `run.sh` through a standard-library installer that brings a hash-verified pip zipapp when the venv has none.

**Question:** Why split the web refactor into 014a/b/c instead of one rewrite, and what does 014a buy the product?

## Answer

A web rewrite mixes three risky changes: framework, templates, and code organization. Doing them together makes regressions hard to attribute and reviews hard to finish.

014a changes only the HTTP boundary and proves it with evidence:

- The same routes, statuses, and HTML.
- 217 passing tests, including Flask test-client coverage of every route and query rule.
- A real fresh-checkout run through `./run.sh`.

014b can then change only the HTML, and 014c only the internal structure, each against a stable base.

What 014a buys: a standard, documented web foundation that new engineers and AI agents recognize; a factory that makes the web layer testable in isolation; and a reproducible, hash-locked dependency process, the first piece of production discipline the cloud deployment will need. It also keeps the benchmark engine free of web code, so the product can later add a scheduler, an API, or a different front end without touching measurement.

## Critique

- **Good:** Small, reviewable, reversible steps, each with a clear "nothing else changed" guarantee. The decision to take a dependency is documented, together with the rules that contain it.
- **Weak:** Users see no change yet, so this step costs time without visible product value. The development server isn't a production server, so deployment work is still ahead.
- **Improve:** Keep 014b and 014c similarly small but schedule them close together, so the refactor turns into visible product work (new views, an API) quickly. Define production serving and configuration as an explicit gate before the first cloud deployment.
