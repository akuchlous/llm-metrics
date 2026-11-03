# Step 018b — Principal engineer

**Step context:** Step 018b added SQLAlchemy Core table metadata, Alembic migration baseline `f1a2b3c4d5e6`, and a bridge for pre-Alembic local SQLite databases.

**Question:** How do you introduce Alembic without losing existing local history, and where did portability remain incomplete?

## Answer

The step distinguishes three cases: a fresh database receives the v7 schema from Alembic; a pre-Alembic SQLite database first runs the existing v0→v7 legacy upgrade and is stamped at head; an Alembic-managed SQLite database upgrades forward. This preserves old rows and avoids replaying baseline DDL on populated databases. However, `connect()` still constructed `sqlite:///` engines, schema inspection still used SQLite `PRAGMA`, and observation deduplication used SQLite-dialect inserts. So the design established a migration framework, **not yet a proven PostgreSQL backend**; the next micro-step must close the dialect boundary.

## Critique

- **Good:** Separates historical compatibility from future schema evolution.
- **Weak:** Claiming PostgreSQL portability from SQLite tests alone overstates the evidence; runtime metadata and Alembic baseline also need parity checks.
- **Improve:** Add explicit URL/driver support, dialect-aware initialization and integration evidence before cloud deployment.
