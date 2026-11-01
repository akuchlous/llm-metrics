# Step 17 — Senior manager

**Step context:** Step 017 was a behavior-preserving cleanup. LiteLLM was evaluated against the Step 016 measurement contract and not adopted: it fetches a price map over the network on import, records zero usage when a provider reports none, sends Gemini and xAI to different endpoints than the request profiles name, and had compromised PyPI releases in March 2026. Duplicated adapter behavior moved into `http_streaming` (`status_failure`, `checked_usage`, `StreamContext`), `real_smoke` now delegates to `real_benchmark.run`, and test fakes are shared. SQLAlchemy Core + Alembic are recommended for the Google Cloud persistence step. Package code shrank by about 150 lines, with no change to wire requests, stored facts, pages or the API.

**Question:** How do you run a cleanup step without it turning into a rewrite or silently changing results?

## Answer

- **Freeze the contract first.** List the invariants (workload bytes, profiles, one request per attempt, unknown ≠ 0, privacy) and test each before touching code. The Step 016 tests already pinned request bodies, profiles and hashes.
- **Measure.** Record LOC and dependencies before and after with a script anyone can rerun, and compare all HTML and API responses byte for byte.
- **Scope by risk.** The database move (SQLAlchemy/Alembic) is assessed and scheduled for the persistence step, where it has a reason to exist, instead of being bundled into a cleanup.
- **Record rejected options with evidence,** so the LiteLLM question does not come back without new facts.

## Critique

- **Good:** It produced a smaller package with zero behavior change and one durable decision.
- **Weak:** The test suite grew, so "less code" is true for the product but not for the repository.
- **Improve:** Track test LOC separately and prune genuinely redundant tests in a later pass, with the coverage map as a guide.
