# Step 17 — Principal engineer

**Step context:** Step 017 was a behavior-preserving cleanup. LiteLLM was evaluated against the Step 016 measurement contract and not adopted: it fetches a price map over the network on import, records zero usage when a provider reports none, sends Gemini and xAI to different endpoints than the request profiles name, and had compromised PyPI releases in March 2026. Duplicated adapter behavior moved into `http_streaming` (`status_failure`, `checked_usage`, `StreamContext`), `real_smoke` now delegates to `real_benchmark.run`, and test fakes are shared. SQLAlchemy Core + Alembic are recommended for the Google Cloud persistence step. Package code shrank by about 150 lines, with no change to wire requests, stored facts, pages or the API.

**Question:** "Prefer mature libraries" is now a project rule. Why was rejecting LiteLLM consistent with it?

## Answer

The rule has explicit exceptions: reuse unless it compromises measurement correctness, security or cost. LiteLLM failed on all three, with evidence from its own source:

- **Correctness:**
  - It fills unreported usage with zeros, which breaks unknown ≠ 0.
  - It normalizes Gemini to `generateContent` and xAI to chat completions, which changes the endpoints our request profiles name.
  - It can rewrite `minimal` thinking to `low` on some models.
- **Security:** it fetches a remote price map at import, and its PyPI releases were compromised in March 2026, in a process that holds four provider keys.
- **Cost:** a large hash-pinned dependency tree, plus escape hatches per provider, to replace about 1,300 lines of tested code.

A benchmark library is not a commodity integration: its job is to observe exactly what the provider did, while a router's job is to make providers look the same. The reusable parts that are commodity (HTTP, JSON, SSE framing) stay on the standard library.

## Critique

- **Good:** The decision is falsifiable: each blocker names a file or behavior to re-check.
- **Weak:** Some evaluation cells (SDK retry overrides, request-id access) were not verified against running code.
- **Improve:** Re-evaluate when LiteLLM, or a smaller library, offers raw-usage passthrough and native Interactions/Responses support, using the adapter tests as the acceptance suite.
