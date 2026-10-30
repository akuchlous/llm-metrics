import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


class CLITest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        # Never write to the developer's real database.
        self.db_path = Path(tmp.name) / "observations.db"

    def run_cli(self, app_env):
        env = {k: v for k, v in os.environ.items() if k != "APP_ENV"}
        env["LLM_METRICS_DB_PATH"] = str(self.db_path)
        if app_env is not None:
            env["APP_ENV"] = app_env
        return subprocess.run(
            [sys.executable, "-m", "llm_metrics"],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_test_env_prints_all_metrics_with_units(self):
        proc = self.run_cli("test")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Provider: dummy", proc.stdout)
        self.assertIn("Model: dummy-model-v1", proc.stdout)
        self.assertRegex(proc.stdout, r"TTFT: \d+\.\d ms")
        self.assertRegex(proc.stdout, r"Total latency: \d+\.\d ms")
        self.assertRegex(proc.stdout, r"Output throughput: \d+\.\d chunks/s")

    def test_test_env_saves_all_metrics_from_one_request(self):
        proc = self.run_cli("test")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Saved 3 observations to", proc.stdout)
        with closing(sqlite3.connect(self.db_path)) as conn:
            rows = conn.execute(
                "SELECT recorded_at, environment, provider, model, metric, value"
                " FROM observations ORDER BY id"
            ).fetchall()
        self.assertEqual([r[4] for r in rows], ["ttft", "total_latency", "output_chunks_per_s"])
        for _, environment, provider, model, _, value in rows:
            self.assertEqual((environment, provider, model), ("test", "dummy", "dummy-model-v1"))
            self.assertGreater(value, 0)
        self.assertEqual(len({r[0] for r in rows}), 1)  # same request, same timestamp
        self.assertGreaterEqual(rows[1][5], rows[0][5])  # total >= TTFT

    def test_prod_env_fails_without_measuring(self):
        proc = self.run_cli("prod")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("Error:", proc.stderr)
        self.assertEqual(proc.stdout, "")
        self.assertFalse(self.db_path.exists())

    def test_invalid_env_fails(self):
        proc = self.run_cli("staging")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("Invalid APP_ENV", proc.stderr)
        self.assertFalse(self.db_path.exists())


if __name__ == "__main__":
    unittest.main()
