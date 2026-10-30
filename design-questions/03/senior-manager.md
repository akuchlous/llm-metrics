# Step 03 — Senior manager

**Question:** How do you make sure tests never pollute a developer's real data?

## Answer

Three mechanisms, plus verification:

1. **Unit tests** pass temporary paths straight to `save_observation` and `load_observations`.
2. **Subprocess tests** (the CLI, seeding, the dashboard) set `LLM_METRICS_DB_PATH` to a temporary file (D020).
3. **The `run.sh` end-to-end test** runs in a temporary copy of the repo, so even its default `data/` path is disposable.

Verification: after running the full suite from a clean checkout, `data/` didn't exist. In a later step, the row count of the real database was identical before and after the suite.

## Critique

- **Good:** Isolation was verified empirically, not just designed, and the override is a single, documented environment variable.
- **Weak:** It's opt-in. Every new subprocess test must remember to set `LLM_METRICS_DB_PATH`, and each test file builds its own environment dictionary (some duplication across `test_cli.py`, `test_seed_history.py` and `test_dashboard.py`). One forgotten line would silently write to a real database.
- **Improve:** Make safety the default: one shared helper that builds a subprocess environment with a temporary database, or a check that fails the suite if `data/llm_metrics.db` changed during the run. Fail-safe defaults scale better than reviewer attention.
