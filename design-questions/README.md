# Software design questions

Interview-style design questions drawn from each completed step of `llm-metrics`. Use them to practise explaining real engineering decisions at different levels of seniority.

Each file covers one numbered step (matching `prompts/NNN-*.md`) and has one question per level:

| Level | What the question probes |
|---|---|
| **Lead engineer** | Concrete technical correctness and tradeoffs in the code. |
| **Principal engineer** | Long-term architecture, failure modes, and when a design stops being right. |
| **Senior manager** | Delivery, process, risk, and team practices. |
| **Director** | Strategy, credibility, cost of decisions, and organisational impact. |

Every question has:

- **Sample answer:** a realistic, decent-but-imperfect answer.
- **Good:** what the answer does well.
- **Weak:** what it misses or gets wrong.
- **Improve:** how a stronger answer would go.

The sample answers are deliberately not perfect; the critique is the learning material. The facts come from the code, `DECISIONS.md`, and `prompts/NNN-output.md`.

| Step | File |
|---|---|
| 001 — TTFT with a dummy provider | [001-initial-ttft.md](001-initial-ttft.md) |
| 002 — One-command local run | [002-local-run-script.md](002-local-run-script.md) |
| 003 — SQLite persistence | [003-sqlite-storage.md](003-sqlite-storage.md) |
| 004 — Simulated history | [004-simulated-history.md](004-simulated-history.md) |
| 005 — Local dashboard | [005-first-ttft-dashboard.md](005-first-ttft-dashboard.md) |
| 006 — TTFT percentiles | [006-ttft-percentiles.md](006-ttft-percentiles.md) |
