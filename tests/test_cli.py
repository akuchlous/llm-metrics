import os
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def run_cli(app_env):
    env = {k: v for k, v in os.environ.items() if k != "APP_ENV"}
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


class CLITest(unittest.TestCase):
    def test_test_env_prints_ttft(self):
        proc = run_cli("test")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Provider: dummy", proc.stdout)
        self.assertIn("Model: dummy-model-v1", proc.stdout)
        self.assertIn("Metric: TTFT", proc.stdout)
        self.assertRegex(proc.stdout, r"TTFT: \d+\.\d ms")

    def test_prod_env_fails_without_measuring(self):
        proc = run_cli("prod")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("Error:", proc.stderr)
        self.assertEqual(proc.stdout, "")

    def test_invalid_env_fails(self):
        proc = run_cli("staging")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("Invalid APP_ENV", proc.stderr)


if __name__ == "__main__":
    unittest.main()
