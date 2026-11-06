# Director — Step 019: one-command disposable Docker local workflow

**Step context:** Step 019 deferred the second OpenAI cloud pilot (Step 018i) to first build a one-command Docker Compose local workflow. The rationale: PostgreSQL integration tests were previously skipped in every local run, leaving a gap between local confidence and cloud behavior.

---

## Question

This project has now spent two steps (018d and 019) investing in a local PostgreSQL test harness. The first real paid measurement (Step 018f) worked correctly against Cloud SQL without any local PostgreSQL infrastructure. What is the organizational argument for investing in local PostgreSQL test coverage, and when does that investment stop paying off?

## Answer

**The argument for local PostgreSQL coverage:**

Step 018d found two real bugs that the SQLite-only test suite had not caught:
1. `spend_by_model` ORDER BY: SQLite permits bare column references in ORDER BY when GROUP BY is present; PostgreSQL's strict GROUP BY does not. The query worked locally and failed in cloud.
2. Fail-closed orphan tables: a silent `alembic stamp head` on an unknown schema needed to become an explicit `RuntimeError` for PostgreSQL, not SQLite.

Both bugs would have caused production failures if deployed without local PostgreSQL validation. The investment in Step 018d was justified by those catches.

**The ongoing return:**
- Local PostgreSQL tests run in every `./run.sh test` cycle, so dialect bugs are caught before code is committed — not after a Cloud Run deployment.
- The disposable Compose database means no developer needs a persistent PostgreSQL installation or manual cleanup.
- The 018h fail-closed guard uses PostgreSQL-specific URL detection; the integration test suite validates that guard's behavior against a real PostgreSQL server.

**When does the investment stop paying off?**

1. *If the storage layer stops changing:* Once the schema and query layer stabilize, the dialect divergence risk shrinks. At that point, running 13 integration tests on every commit is a maintenance cost with diminishing returns.

2. *If Alembic migrations are the primary change surface:* Migration correctness is better validated by a dedicated migration test (apply, verify, rollback) than by the full 13-test suite. A narrower migration test harness would run faster and be easier to maintain.

3. *If a managed CI PostgreSQL service replaces local Docker:* GitHub Actions provides a free PostgreSQL service container for CI jobs. If CI always runs the integration tests, the local Compose infrastructure is redundant for the validation use case (though it still provides the development workflow value).

**Strategic view:** The local Docker investment is a bridge. It closes the gap between local development and cloud deployment while the team is too small and the deployment cadence too low to justify a dedicated CI pipeline. Once CI is established, the local PostgreSQL Compose harness becomes a convenience rather than a necessity.

## Critique

**Good:** Investing in local PostgreSQL before the second cloud pilot reduces the probability of a paid test failing due to dialect bugs. Finding and fixing bugs locally costs nothing; finding them in a Cloud Run job costs $0.0003 per attempt plus developer time.

**Weak:** The step deferred the second cloud pilot (018i) to build tooling. From a product perspective, the second pilot is a dependency for publishable results. Each tooling investment step is a delay to the publishable benchmark, not a contribution to it. The tradeoff is real: more investment in local correctness reduces cloud pilot risk but also delays the moment when the project produces results worth sharing.

**How to improve:** Cap local infrastructure investment at the point where it starts delaying publishable milestones. The right trigger to stop investing in local tooling is when the cloud pilot succeeds twice in a row without local-PostgreSQL-caught bugs. After that, maintenance mode for the Compose harness and investment in cloud measurement quality.
