# Step 15 — Senior manager

**Step context:** Step 015 added a code-defined catalogue of versioned benchmark workloads (`llm_metrics/workloads.py`). Six candidate workloads (`interactive-chat-v1`, `coding-v1`, `rag-v1`, `summarization-v1`, `extraction-v1`, `agent-tool-v1`) each fix one deterministic synthetic prompt (about 2K to 32K tokens by a 4-characters-per-token estimate) and an output cap (150 to 1000). `benchmark.run_attempt` now takes a catalogue workload, sends exactly its prompt and cap, stores its versioned id, and refuses anything that is not the catalogue definition. Prompts are pinned by SHA-256 tests and never stored. No paid calls were made.

**Question:** User research is still running. Why commit to six workloads now, and what happens if research says one is wrong?

## Answer

Engineering needs a defined workload to measure anything meaningful, and research needs something concrete to react to. The six are labelled hypotheses in code, docs and decisions, so nobody mistakes them for validated demand.

Changing them is cheap by design:
- **Add one:** one `Workload(...)` entry and its pinned hash; providers, storage, analytics and the web layer need no change.
- **Reshape one:** create `rag-v2` next to `rag-v1`. Old data keeps its meaning and stays separate.
- **Drop one:** remove it from the runnable catalogue; stored rows keep their id.

What it cost: one new module, a signature change to `run_attempt` (all callers migrated, no dual API), and 21 new tests. No schema change, no paid calls.

## Critique

- **Good:** Engineering is not blocked by research, and research findings map onto concrete, versioned artefacts.
- **Weak:** Without a written process, "retire" and "new version" decisions could be made ad hoc by whoever edits the file.
- **Improve:** Name an owner for catalogue changes and record each change (with its research evidence) as a decision entry.
