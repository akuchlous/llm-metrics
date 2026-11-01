# Step 17 — Director

**Step context:** Step 017 was a behavior-preserving cleanup. LiteLLM was evaluated against the Step 016 measurement contract and not adopted: it fetches a price map over the network on import, records zero usage when a provider reports none, sends Gemini and xAI to different endpoints than the request profiles name, and had compromised PyPI releases in March 2026. Duplicated adapter behavior moved into `http_streaming` (`status_failure`, `checked_usage`, `StreamContext`), `real_smoke` now delegates to `real_benchmark.run`, and test fakes are shared. SQLAlchemy Core + Alembic are recommended for the Google Cloud persistence step. Package code shrank by about 150 lines, with no change to wire requests, stored facts, pages or the API.

**Question:** Why spend a step on cleanup and a library evaluation right before the paid pilot and cloud deployment?

## Answer

Because both next steps raise the cost of change:

- **Before the pilot:** once real data exists, any change to request shapes or usage handling splits the history. Confirming now that the adapters are the right foundation protects the first real dataset.
- **Before deployment:** a hosted runner holds four provider keys. Choosing not to add a dependency with a recent credential-stealing compromise, and that makes network calls on import, is a security decision that is cheaper before deployment than after.
- **For the persistence move:** the SQLAlchemy/Alembic recommendation means that step starts with a plan instead of a debate.

The step also keeps credibility: "independent measurement" means we can show exactly what was sent and what the provider reported, which a normalizing router would blur.

## Critique

- **Good:** Low-risk work that removes future risks and records why.
- **Weak:** It delays visible product progress by a step.
- **Improve:** Keep cleanup steps rare and evidence-driven, and fold small cleanups into feature steps once the review checklist's reuse question is routine.
