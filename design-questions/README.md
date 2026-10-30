# Software design questions

## Purpose

This directory turns each completed `llm-metrics` implementation step into reusable software-design learning and interview practice.

The questions are not a separate theoretical curriculum. They are derived from code that was actually built: each answer should explain the real implementation, its tradeoffs and failure modes, then critique how the design or answer could be stronger.

The reusable requirements for creating new step folders live in `prompts/DESIGN_QUESTIONS.md`.

## Structure

Each step has a folder matching its prompt number, with one file per engineering level:

```text
design-questions/
  01/
    lead-engineer.md
    principal-engineer.md
    senior-manager.md
    director.md
  02/
    ...
```

| Level | What the question probes |
|---|---|
| **Lead engineer** | Concrete technical correctness and tradeoffs in the code. |
| **Principal engineer** | Long-term architecture, failure modes, and when a design stops being right. |
| **Senior manager** | Delivery, process, risk, and team practices. |
| **Director** | Strategy, credibility, cost of decisions, and organisational impact. |

Each file has:

- **Step context:** one line on what that step built, so the file stands alone.
- **Question and answer:** role-appropriate reasoning grounded in the real implementation, `DECISIONS.md`, and `prompts/NNN-output.md`.
- **Critique:** what was **good**, what was **weak or missing**, and how to **improve** the answer or design.

## Step index

| Step | Topic | Prompt |
|---|---|---|
| [01](01/) | TTFT with a dummy provider | `prompts/001-initial-ttft.md` |
| [02](02/) | One-command local run | `prompts/002-local-run-script.md` |
| [03](03/) | SQLite persistence | `prompts/003-sqlite-storage.md` |
| [04](04/) | Deterministic simulated history | `prompts/004-simulated-history.md` |
| [05](05/) | First local dashboard | `prompts/005-first-ttft-dashboard.md` |
| [06](06/) | TTFT percentiles | `prompts/006-ttft-percentiles.md` |
| [07](07/) | TTFT time windows | `prompts/007-time-windows.md` |
| [08](08/) | Total response latency | `prompts/008-total-response-latency.md` |
| [09](09/) | Output throughput | `prompts/009-throughput.md` |
| [10](10/) | Token accounting and cost | `prompts/010-token-accounting-and-cost.md` |
| [11](11/) | Errors and availability | `prompts/011-errors-and-availability.md` |
| [12](12/) | First real provider and benchmark spend | `prompts/012-first-real-provider.md` |
| [12a](12a/) | Live validation cleanup and request traceability | `prompts/012a-live-validation-cleanup.md` |
