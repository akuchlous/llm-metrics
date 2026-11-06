# Senior manager — Step 019: one-command disposable Docker local workflow

**Step context:** Step 019 replaced the native-Python `./run.sh` with a Docker Compose wrapper that runs the full test suite (including live PostgreSQL integration tests), seeds simulated data, runs a measurement, and serves the dashboard — all without installing Python, PostgreSQL, or pip on the developer's host machine.

---

## Question

The team made Docker a hard prerequisite for `./run.sh`. A developer without Docker gets an error message and cannot run any local tests at all. What was the tradeoff, what was the alternative, and how would you assess whether the decision was right for the team?

## Answer

**The decision:** Docker and `docker compose` are now checked at the start of `run.sh`; the script exits with a helpful error if either is absent. There is no native-Python fallback path.

**The tradeoff:**
- *Before:* `./run.sh` worked with only Python 3.10+ installed. Any developer could run the full workflow on a bare machine. PostgreSQL integration tests were skipped if `TEST_POSTGRES_URL` was not set.
- *After:* PostgreSQL integration tests run in every local test cycle because the Compose DB is always available. Test coverage is higher, but every developer now needs Docker.

**The alternative that was explicitly rejected:** Keep the native-Python path as a fallback when Docker is absent. This would preserve accessibility for developers without Docker but would re-create two code paths for `./run.sh`, two sets of documentation, and ongoing drift as the Docker path adds features the native path does not follow.

**Assessment criteria:**
1. *Team Docker adoption:* If every developer and CI runner already has Docker, the cost of the new prerequisite is zero. If some developers are on locked-down machines that cannot install Docker, the cost is high.
2. *Test value vs. install friction:* PostgreSQL integration tests found two real bugs in Step 018d (GROUP BY ordering, fail-closed schema detection). Making them always run is valuable. The question is whether that value exceeds the install friction.
3. *Verification gap:* The Docker workflow itself was not verified on the development machine (Docker unavailable) and is marked UNVERIFIED pending Cloud Shell validation. This is a risk: the documented workflow may have bugs that only appear when Docker runs it. A team would want CI to close this gap.

**Was the decision right?** For this single-developer project where Docker is available in Cloud Shell and every GCP deployment already uses containers, it was reasonable. For a broader team or an environment without Docker, the cost/benefit would need re-evaluation.

## Critique

**Good:** The decision eliminates the two-path maintenance burden and makes PostgreSQL integration tests a first-class part of the development cycle. The error message is clear and includes a Docker installation link.

**Weak:** The Docker workflow is UNVERIFIED at step completion because Docker is unavailable on the development machine. This is acknowledged in `019-output.md`, but it means the step's acceptance criteria are partially deferred to Cloud Shell validation. A well-managed team would not ship a step as complete with UNVERIFIED integration tests.

**How to improve:** Add a CI step (GitHub Actions, Cloud Build trigger, or equivalent) that runs `./run.sh test` on every push to main. This would verify the Docker workflow automatically and catch regressions before ChatGPT review. The Cloud Build path already exists from Step 018f and could be extended.
