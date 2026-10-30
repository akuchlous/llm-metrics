# Step 05 — Principal engineer

**Step context:** Step 005 added a stdlib-only local dashboard on `127.0.0.1` (HTML + server-rendered SVG chart, no JavaScript), started at the end of `./run.sh`.

**Question:** The dashboard binds to `127.0.0.1` with a strict CSP. Is it secure? What did we miss?

## Answer

Controls in place:

- **Binding:** the host is the constant `127.0.0.1` (D026), not configurable, so other machines can't reach it.
- **Script injection:** the page has no JavaScript, and the CSP is `default-src 'none'; style-src 'unsafe-inline'`, so nothing executes or loads externally even if markup were injected.
- **Output encoding:** provider and model are escaped. Timestamps are parsed into datetimes and numbers are formatted, so no raw database text reaches the HTML.
- **Surface:** read-only, a single route, and SQL parameters throughout.

What's missing: **DNS rebinding**. A malicious website open in the same browser can make its own hostname resolve to `127.0.0.1`, and the browser will then let that page read `http://<attacker-host>:8000/`, because the server never checks the `Host` header. Today the impact is low (read-only, simulated data), but it's the standard attack on local developer servers.

## Critique

- **Good:** Layered defences appropriate to the current data, verified with tests (loopback binding, CSP header present, 404 for other paths).
- **Weak:** The threat model wasn't written down, so the rebinding gap went unnoticed until this review. "Local only" was treated as "trusted".
- **Improve:** Add a `Host` check (allow only `127.0.0.1:<port>` and `localhost:<port>`, otherwise 400) before any real or sensitive data is shown. It's a few lines plus a test. Write a short threat model in `DECISIONS.md`: a local attacker, a malicious web page, and a shared machine.
