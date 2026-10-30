# Software design questions

Interview-style design questions drawn from each completed step of `llm-metrics`, answered from what the project actually did, then critiqued.

Each step has a folder matching its prompt number, with one file per level:

```text
design-questions/
  01/  lead-engineer.md  principal-engineer.md  senior-manager.md  director.md
  02/  ...
```

| Level | What the question probes |
|---|---|
| **Lead engineer** | Concrete technical correctness and tradeoffs in the code. |
| **Principal engineer** | Long-term architecture, failure modes, and when a design stops being right. |
| **Senior manager** | Delivery, process, risk, and team practices. |
| **Director** | Strategy, credibility, cost of decisions, and organisational impact. |

Each file has:

- **Step context:** one line on what that step built, so the file stands alone.
- **Answer:** a strong answer grounded in the real implementation, decisions (`DECISIONS.md`) and step reports (`prompts/NNN-output.md`).
- **Critique:** what was **good** about the decision or answer, what was **weak**, and how to **improve** it.

| Step | Topic | Prompt |
|---|---|---|
| [01](01/) | TTFT with a dummy provider | `prompts/001-initial-ttft.md` |
| [02](02/) | One-command local run | `prompts/002-local-run-script.md` |
| [03](03/) | SQLite persistence | `prompts/003-sqlite-storage.md` |
| [04](04/) | Deterministic simulated history | `prompts/004-simulated-history.md` |
| [05](05/) | First local dashboard | `prompts/005-first-ttft-dashboard.md` |
| [06](06/) | TTFT percentiles | `prompts/006-ttft-percentiles.md` |
| [07](07/) | TTFT time windows | `prompts/007-time-windows.md` |
