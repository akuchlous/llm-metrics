# Step 005 — First local dashboard

## Lead engineer: Why standard-library `http.server` and a server-rendered SVG instead of Flask plus a JS charting library?

**Sample answer:** The prompt asked for the smallest *justified* dependency, and none was justified for one static page. Adding Flask would need pip in a venv that doesn't have it, plus a network install on first run. An SVG polyline is enough for a line chart.

- **Good:** Reasons from current requirements and existing constraints (D012), not habit.
- **Weak:** Doesn't state what was given up: tooltips, zoom, and live refresh. Nor the point at which the choice flips; hand-rolled chart code grows fast with axes, ticks, multiple series and legends.
- **Improve:** State the exit criterion: "when we need interaction or multiple series, a small vendored JS chart library beats growing our own SVG code." Keep rendering isolated (`render_page`, `_chart_svg`) so swapping it is cheap.

## Principal engineer: The dashboard binds to `127.0.0.1` with a strict CSP. Is it secure? What did we miss?

**Sample answer:** Yes. It's only reachable from the local machine, it has no JavaScript, the CSP blocks external loads, and dynamic values are escaped or come from parsed numbers and timestamps.

- **Good:** Covers network exposure, script injection, and output encoding.
- **Weak:** "Only reachable locally" isn't the whole story. A malicious website open in the same browser can use **DNS rebinding** to make the browser send requests to `127.0.0.1:8000` and read the responses, because the server doesn't validate the `Host` header. The impact here is low (read-only, simulated data), but the pattern will matter once real data or write endpoints exist.
- **Improve:** Name the threat model explicitly (local attacker vs. malicious web page), and add the cheap mitigation when the data becomes sensitive: reject requests whose `Host` isn't `127.0.0.1:<port>` or `localhost:<port>`. Distinguish "secure for current data" from "secure pattern".

## Senior manager: `./run.sh` changed from "runs and exits" to "keeps serving until Ctrl+C". How do you handle a behaviour change like that?

**Sample answer:** We documented it in the README, the decisions file, and the step report, and updated the end-to-end test.

- **Good:** It was recorded where people look, and the test captures the new contract.
- **Weak:** Doesn't consider who depended on the old behaviour: scripts, habits, any future CI that runs `./run.sh` and expects it to finish. Breaking a "contract" command deserves explicit communication, not just docs.
- **Improve:** Flag it as a breaking change in the review and the commit message, and consider a way to keep the old behaviour where it's needed (for example, a mode that measures and exits) once a real consumer needs it. Ask who is affected before changing it.

## Director: What would make this dashboard credible to people outside the team?

**Sample answer:** Clear labelling, accurate charts, and real data once providers are integrated.

- **Good:** Recognises that labelling and accuracy are prerequisites.
- **Weak:** Credibility for an independent benchmark comes mostly from methodology transparency, not visuals: how TTFT is measured, from where, how often, with what prompts, and how outliers are handled. None of that is mentioned.
- **Improve:** Publish the methodology next to the numbers, and make the dataset and code reproducible (already a project strength). Show sample sizes and percentile methods on the page, and keep a changelog of methodology changes so trends stay comparable.
