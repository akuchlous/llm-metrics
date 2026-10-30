# Step 04 — Principal engineer

**Step context:** Step 004 added a command that seeds 168 deterministic hourly simulated TTFT rows for a fixed week, idempotently via a unique index and `INSERT OR IGNORE`.

**Question:** The history uses a fixed calendar week, not "the last 7 days". Defend or attack that.

## Answer

Two separate properties are involved:

1. **Deterministic values:** a fixed random seed (`random.Random(4)`) gives identical values on every machine.
2. **Stable timestamps:** a fixed anchor (`2026-10-23 00:00 UTC`) gives identical timestamps on every run.

Fixing both made idempotence trivial: the same 168 primary facts every time, deduplicated by the unique index. A window relative to "now" would need values keyed by hour offset, and would insert new rows whenever the clock crossed an hour, re-seeding partial history.

The cost is that the data ages. Any "recent" view eventually shows none of it. The dashboard therefore shows all data with no time window (D027), and the next prompt had to require that the history stay visible however old it is.

## Critique

- **Good:** Fully reproducible test data. Screenshots from the cloud container and the owner's Chromebook showed identical spikes, which is a nice proof of determinism.
- **Weak:** The decision quietly constrained later features: time windows and "recent" views now conflict with test data. That downstream cost wasn't recorded when the decision was made.
- **Improve:** Record downstream constraints with a decision ("prevents meaningful last-N-days views"). When time-window features arrive, generate history relative to a stored anchor (seeded once per database), keeping values deterministic and timestamps recent.
