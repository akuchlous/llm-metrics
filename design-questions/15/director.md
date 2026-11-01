# Step 15 — Director

**Step context:** Step 015 added a code-defined catalogue of versioned benchmark workloads (`llm_metrics/workloads.py`). Six candidate workloads (`interactive-chat-v1`, `coding-v1`, `rag-v1`, `summarization-v1`, `extraction-v1`, `agent-tool-v1`) each fix one deterministic synthetic prompt (about 2K to 32K tokens by a 4-characters-per-token estimate) and an output cap (150 to 1000). `benchmark.run_attempt` now takes a catalogue workload, sends exactly its prompt and cap, stores its versioned id, and refuses anything that is not the catalogue definition. Prompts are pinned by SHA-256 tests and never stored. No paid calls were made.

**Question:** What does a workload catalogue change about the credibility of LLM Metrics, and what claims must we still avoid?

## Answer

It moves results from "a request took 3.6 s" to "under `rag-v1`, from this origin, with caching disabled, the request took 3.6 s". A reader can reproduce the workload exactly: the content is public, deterministic and versioned. That is the basis for any comparison we later publish.

Claims we must still avoid:
- that these six are the workloads users care most about (they are hypotheses);
- any quality or "best model" claim (answers are not evaluated);
- cross-provider comparisons today (no workload has yet been run on a real provider);
- equal-token fairness (providers tokenize differently; we report their counts).

## Critique

- **Good:** Reproducible, original methodology that is safe to publish and easy to explain.
- **Weak:** Synthetic, templated content may not reflect real application text, and the methodology has no external review yet.
- **Improve:** Publish the methodology only with real multi-provider data and its limitations, and invite users to propose workloads.
