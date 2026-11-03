# Step 018a — Principal engineer

**Step context:** Step 018a documented the OpenAI vertical-slice architecture and identified durable storage, unattended execution, scheduling, and real-data read surfaces as separate gaps.

**Question:** Why validate one provider end to end before simultaneously productionizing the four existing adapters?

## Answer

The existing adapters already share a measurement contract, but the product's operational loop is incomplete: local SQLite is not container-durable, scheduled execution and spend guardrails do not exist, and aggregate HTML/JSON still select simulated dummy data. Implementing all four live providers first would increase integration variables without proving durability, reproducibility or truthful analytics. The chosen architecture stages one exact OpenAI workload/profile through durable persistence, a bounded runner, cloud execution and real-data reporting. Other providers can then reuse the proven execution and product surface.

## Critique

- **Good:** Isolates operational risk and makes the measurement pipeline independently useful early.
- **Weak:** Single-provider success does not demonstrate cross-provider comparability or all adapter contracts.
- **Improve:** After the OpenAI pilot, onboard one provider per reviewed step and keep each profile's reasoning/cache conditions visible rather than assuming equivalence.
