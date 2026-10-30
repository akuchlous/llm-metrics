# Step 04 — Lead engineer

**Step context:** Step 004 added a command that seeds 168 deterministic hourly simulated TTFT rows for a fixed week, idempotently via a unique index and `INSERT OR IGNORE`.

**Question:** How is re-seeding made idempotent? Compare it with the alternatives.

## Answer

A unique index on (`recorded_at`, `environment`, `provider`, `model`, `metric`), with seeding done by `INSERT OR IGNORE` through `executemany`. The cursor's `rowcount` reports how many rows were actually inserted (`168 new`, then `0 new, 168 already present`). The index is created with `CREATE UNIQUE INDEX IF NOT EXISTS`, so Step 003 databases gain it with no migration; a test builds an old-schema database and seeds it twice.

Alternatives considered:

| Option | Pros | Cons |
|---|---|---|
| Unique index + `INSERT OR IGNORE` (chosen) | Enforced by the database, no schema change | Also constrains live inserts |
| `source` column (seeded / live) | Explicit provenance, easy filtering | Needs `ALTER TABLE` on existing databases |
| "already seeded" marker table | Trivial check | Can drift from the actual rows; not enforced |
| Delete then re-insert | Simple | Destroys data; not concurrency-safe |

Live saves deliberately keep a plain `INSERT`, so the CLI can never print "Saved" for a row that was silently ignored.

## Critique

- **Good:** The smallest correct change, enforced by the database, with a backward-compatibility test.
- **Weak:** Seeded and live rows are only distinguishable by timestamp, and this choice later forced the dashboard and percentiles to mix them (see 06). The unique index also applies to live data, which is harmless now but is a constraint nobody asked for.
- **Improve:** When the next schema change happens anyway (with versioning, see 03), add a `source` column and stop relying on timestamps to tell seeded and live rows apart.
