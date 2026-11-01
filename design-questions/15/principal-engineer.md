# Step 15 — Principal engineer

**Step context:** Step 015 added a code-defined catalogue of versioned benchmark workloads (`llm_metrics/workloads.py`). Six candidate workloads (`interactive-chat-v1`, `coding-v1`, `rag-v1`, `summarization-v1`, `extraction-v1`, `agent-tool-v1`) each fix one deterministic synthetic prompt (about 2K to 32K tokens by a 4-characters-per-token estimate) and an output cap (150 to 1000). `benchmark.run_attempt` now takes a catalogue workload, sends exactly its prompt and cap, stores its versioned id, and refuses anything that is not the catalogue definition. Prompts are pinned by SHA-256 tests and never stored. No paid calls were made.

**Question:** Why define fairness as "same content" rather than "same number of input tokens", and what does that imply for comparisons?

## Answer

Token counts are not a property of the text; they depend on each provider's tokenizer and request wrapping. Forcing equal counts would mean different text per provider, so providers would no longer be doing the same task, and we would need every provider's tokenizer as a dependency.

So for a workload version:
- the input text and task semantics are identical across providers;
- each provider's reported `input_tokens` and `output_tokens` are stored as facts;
- `target_input_tokens` is only a design label (~4 characters per token).

Implications:
- **Latency per request** is comparable: same work asked, measured end to end.
- **Cost** is comparable per request; cost per token is not a fair cross-provider unit on its own.
- **Throughput** in tokens/s uses each provider's own token unit, so it is not directly comparable across providers; per-request latency and output characters per second are safer cross-provider figures.
- **Output length** varies: the cap is a maximum, and nothing retries to reach it. A model that answers in 50 tokens and one that uses 300 did different amounts of generation; reports must show output tokens beside latency.

## Critique

- **Good:** Avoids a hidden normalization step that would make results untraceable, and keeps zero new dependencies.
- **Weak:** The size targets are unvalidated estimates; code and numbers tokenize denser than prose, so real counts may land well off target. Tokens/s comparisons across providers remain easy to misread.
- **Improve:** After the first real runs, publish observed input tokens per provider per workload, and consider a provider-neutral throughput (characters/s) for cross-provider views.
