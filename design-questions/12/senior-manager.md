# Step 12 — Senior manager

**Step context:** Step 012 added the first real provider: an OpenAI `gpt-6-luna` adapter on the Responses API using only the standard library, run solely by the explicit `python -m llm_metrics.real_smoke` (one paid call, key from `OPENAI_API_KEY`, stored as `prod`), plus a real-data-only Benchmark API Spend page and clear real-versus-simulated labelling. Follow-up: the owner verified the price ($0.10 / $0.50 per 1M); the first live call failed as `provider_error`, so sanitized `--debug` diagnostics and `reasoning.effort: none` were added.

**Question:** This step introduced real money and real credentials. How do you keep spend and secret risk under control on a team where anyone can run the code?

## Answer

Spend controls:

- **Opt-in by construction.** The only paid path is `python -m llm_metrics.real_smoke`. `./run.sh`, the simulated CLI, the dashboard, migrations, imports and tests can't call OpenAI; tests assert this with blocked sockets. `APP_ENV=prod ./run.sh` still refuses.
- **Bounded per run.** Exactly one call, no loop, no retry, `max_output_tokens` 64, a fixed one-sentence prompt, no tools, and `store: false`. It announces "exactly ONE paid API request" before calling.
- **Visible after the fact.** Every call's cost and rates are stored, and the Benchmark API Spend page totals them per model and overall.

Secret controls:

- The key comes from `OPENAI_API_KEY` at call time and is never stored, printed, logged, or included in errors or `repr`. A test searches printed output and the database bytes for it. There's no `.env` loading, and `.env` is git-ignored.

Process:

- **Asked before implementing:** the price couldn't be verified and the API wasn't reachable, so I asked how to proceed rather than guessing. The choices are recorded in the step report's "Choices made" section.

## Critique

- **Good:** Spend is opt-in, bounded and transparent; the secret never touches disk; and decisions under uncertainty went to the owner instead of being guessed.
- **Weak:** There's no hard budget limit: someone can run `real_smoke` in a shell loop. Nothing checks the provider-side invoice against our computed spend. Keys in shell history or environment variables are still a local risk.
- **Improve:** Add a simple local guard (e.g. refuse when today's recorded real spend exceeds a configured cap). Set a monthly hard limit and a project-scoped key in the OpenAI account. Periodically reconcile the spend page against OpenAI's usage dashboard and record any difference.
