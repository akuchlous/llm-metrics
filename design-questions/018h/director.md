# Step 018h — Director

**Step context:** Step 018h adds a fail-closed guard in `real_benchmark.run()` that
rejects non-local-origin paid benchmark calls unless `LLM_METRICS_DATABASE_URL` is
explicitly set to a PostgreSQL URL, and provides an analysis of durable-storage
options for the next benchmark collection session.

**Question:** The storage analysis in 018h compares Cloud SQL, Cloud Storage, and
serverless SQL, recommending Cloud SQL provisioned per session at ~$9–11/month idle.
Given the locked product direction of static public delivery (D069) and the
long-term goal of a Router/Xchange consuming versioned JSON snapshots, what is the
strategic case for or against committing to Cloud SQL as the measurement store?

## Answer

The case for Cloud SQL per session is pragmatic: it is the only fully proven option
in this project (018f), requires no code changes, and the ~$9–11/month idle cost is
eliminated by deleting the instance between sessions. For a project collecting
one or two benchmark sessions per month, the per-session cost is a few dollars of
compute plus API fees (~$0.0003/request × n runs). That is well within budget and
defensible while the dataset is small.

The case against committing to Cloud SQL long-term rests on the product direction:
D069 says the public site will be static HTML and versioned JSON snapshots, not a
continuously running database. If the benchmark eventually runs on a schedule (e.g.
daily), a continuously provisioned Cloud SQL instance costs ~$9–11/month regardless
of query volume, and that cost competes with the actual API measurement budget.

The strategic decision point arrives when scheduling is added. At that point:
- If runs are infrequent (weekly or less), the per-session Cloud SQL pattern
  (provision → measure → export → delete) remains viable and cost-efficient.
- If runs are frequent (daily or more), the idle cost of Cloud SQL becomes the
  dominant cost item. Cloud Storage with a lightweight append-only record format
  becomes attractive, but it requires significant engineering work to replace the
  SQLAlchemy storage layer. Alternatively, a Cloud SQL instance with auto-stop
  between runs would reduce idle cost at the expense of startup latency.

The right decision now: do not replace Cloud SQL. Land 018h's guard and the
per-session Cloud SQL pattern for 018i. Revisit storage architecture when a
schedule cadence is defined — that is when the cost/complexity tradeoff becomes
concrete rather than speculative.

This is consistent with the project's established principle: "add structure only
when current requirements justify it" (DECISIONS.md). The static-site product
direction does not require a continuously available database; it requires that each
run's data is durably captured before being exported to the static pipeline.

## Critique

- **Good:** The analysis is honest about what is proven (Cloud SQL) versus
  hypothetical (Cloud Storage backend, AlloyDB Serverless) and explicitly declines
  to recommend an unproven option. The recommendation matches the project's current
  scale and avoids premature optimization.
- **Weak:** The analysis does not quantify the break-even point at which Cloud
  Storage becomes cheaper than Cloud SQL (approximately when API + operational costs
  per session exceed ~$9/month, i.e. >30,000 requests/month at $0.0003 each). That
  number would make the future architectural decision more concrete.
- **Improve:** When defining the benchmark schedule in 018i/018j, record the
  expected run frequency in DECISIONS.md alongside the storage choice. That
  makes the cost model and the revisit trigger explicit rather than implicit.
