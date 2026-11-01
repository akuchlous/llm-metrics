# Step 15 — Lead engineer

**Step context:** Step 015 added a code-defined catalogue of versioned benchmark workloads (`llm_metrics/workloads.py`). Six candidate workloads (`interactive-chat-v1`, `coding-v1`, `rag-v1`, `summarization-v1`, `extraction-v1`, `agent-tool-v1`) each fix one deterministic synthetic prompt (about 2K to 32K tokens by a 4-characters-per-token estimate) and an output cap (150 to 1000). `benchmark.run_attempt` now takes a catalogue workload, sends exactly its prompt and cap, stores its versioned id, and refuses anything that is not the catalogue definition. Prompts are pinned by SHA-256 tests and never stored. No paid calls were made.

**Question:** How do you guarantee that a stored `workload_id` always means the same request content, today and a year from now?

## Answer

Three guards, each at a different point:

1. **Definition time.** `Workload` is a frozen dataclass validated in `__post_init__`: the id must be versioned and end in its `version`, the category must be known, and sizes must be positive. Benchmark ids must also follow the canonical `<category>-v<version>` form (tested).
2. **Run time.** `benchmark.run_attempt` refuses a workload unless it equals `workloads.get_workload(workload.workload_id)`, field by field and including the prompt. An edited copy (`dataclasses.replace(RAG_V1, prompt=...)`) or an invented `rag-v9` fails before pricing, the provider call, or any write. So no code path can store `rag-v1` for content other than the catalogue's.
3. **Change time.** `tests/test_workloads.py` pins a SHA-256 for every released prompt and rebuilds them in a fresh interpreter with a different hash seed. Editing a released prompt fails CI with "add a new version instead".

The content itself has no randomness, dates, environment or files; it is templates plus integer arithmetic over fixed name lists.

## Critique

- **Good:** Integrity is enforced, not just documented; the failure message tells the next engineer what to do.
- **Weak:** The hash only covers the prompt and the cap's value via equality. The provider request shape (e.g. OpenAI `reasoning.effort`) is outside the workload, so changing an adapter setting silently changes conditions under the same id.
- **Improve:** In Step 016, make each adapter declare a versioned request profile and store it beside `workload_id`, or fold it into the measurement population explicitly.
