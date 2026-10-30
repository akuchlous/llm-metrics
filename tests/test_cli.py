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

    def test_test_env_prints_ttft(self):
        proc = self.run_cli("test")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Provider: dummy", proc.stdout)
        self.assertIn("Model: dummy-model-v1", proc.stdout)
        self.assertIn("Metric: TTFT", proc.stdout)
        self.assertRegex(proc.stdout, r"TTFT: \d+\.\d ms")

    def test_test_env_saves_one_observation(self):
        proc = self.run_cli("test")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Saved observation to", proc.stdout)
        with closing(sqlite3.connect(self.db_path)) as conn:
            rows = conn.execute(
                "SELECT environment, provider, model, metric, value_ms FROM observations"
            ).fetchall()
        self.assertEqual(len(rows), 1)
        environment, provider, model, metric, value_ms = rows[0]
        self.assertEqual((environment, provider, model, metric),
                         ("test", "dummy", "dummy-model-v1", "ttft"))
        self.assertGreater(value_ms, 0)

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
