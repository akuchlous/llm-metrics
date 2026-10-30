# Step 03 — Director

**Question:** Is SQLite the right storage choice? What does reversing it cost later?

## Answer

Yes, for the current product. It's in Python's standard library, needs no server or credentials, costs nothing, works offline on a Chromebook, and comfortably handles this data volume. Hourly measurements for dozens of provider/model pairs stay in the low millions of rows for years.

Reversal cost is kept low by design: **all SQL lives in `storage.py`** (a schema and a handful of small functions), and callers pass and receive plain dicts and tuples. Moving to Postgres would mean rewriting one module, translating a few SQLite-isms (`INSERT OR IGNORE`, text timestamps), and migrating the data.

The realistic triggers to move are not scale. They're **sharing and concurrency**: collectors on several machines writing to one store, or hosting results publicly.

## Critique

- **Good:** The right tool for the stage, with a deliberately small surface area for a later change.
- **Weak:** Some coupling has already crept in: `INSERT OR IGNORE`, text timestamps, and assumptions of a single writer. And there's no backup or export story. The only copy of the measurements is one local file, which matters once data becomes real.
- **Improve:** Name the move triggers in `DECISIONS.md`. Add a simple export (CSV or JSON) before real data exists, so results are portable and backed up regardless of the database.
