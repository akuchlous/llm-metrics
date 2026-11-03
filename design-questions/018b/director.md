# Step 018b — Director

**Step context:** Step 018b invested in portable database tooling before deploying the first OpenAI-only Metrics experiment, preserving local development and avoiding paid calls.

**Question:** Was SQLAlchemy Core plus Alembic the right investment for a very small benchmark data volume?

## Answer

The short-term volume does not need enterprise database features, but a durable managed relational store is contemplated for an unattended cloud benchmark. The existing schema has many fact-level constraints, joins and all-or-nothing writes. SQLAlchemy Core retains explicit SQL-oriented logic without ORM complexity; Alembic gives an auditable forward migration path. This is a scoped investment in correctness and maintainability rather than scale. Actual hosting cost and PostgreSQL behavior remain unverified in Step 018b.

## Critique

- **Good:** Avoids writing a separate hand-maintained PostgreSQL storage implementation and keeps the eventual deployment pathway clear.
- **Weak:** Dependency and migration complexity arrived before any proven multi-day experiment.
- **Improve:** Validate the smallest managed storage option and recurring cost at the next infrastructure decision; reverse course if the solution exceeds the bounded product's needs.
