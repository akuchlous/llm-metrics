import os
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import unittest
import urllib.request
from contextlib import closing
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUN_SH = REPO_ROOT / "run.sh"

# run.sh runs the whole test suite, which includes this file. The end-to-end test
# sets this variable when it calls run.sh so the nested run skips it (no recursion).
NESTED = "LLM_METRICS_INSIDE_RUN_SH_TEST"


def run_until_dashboard(cwd, env):
    """Run ./run.sh. If it reaches the dashboard, fetch the page and stop it.

    Returns (returncode, stdout, stderr, page). page is None if no dashboard started.
    """
    proc = subprocess.Popen(
        ["./run.sh"], cwd=cwd, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    watchdog = threading.Timer(120, proc.kill)  # never hang the test suite
    watchdog.start()
    try:
        stdout, page = "", None
        for line in proc.stdout:
            stdout += line
            if line.startswith("Dashboard: "):
                url = line.split()[1]
                with urllib.request.urlopen(url, timeout=10) as response:
                    page = response.read().decode("utf-8")
                proc.terminate()
                break
        returncode = proc.wait(timeout=30)
        return returncode, stdout, proc.stderr.read(), page
    finally:
        watchdog.cancel()
        proc.stdout.close()
        proc.stderr.close()


class RunScriptTest(unittest.TestCase):
    def test_is_executable(self):
        self.assertTrue(os.access(RUN_SH, os.X_OK))

    def test_bash_syntax(self):
        subprocess.run(["bash", "-n", str(RUN_SH)], check=True)

    @unittest.skipIf(os.environ.get(NESTED), "already running inside run.sh")
    def test_end_to_end_in_a_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Copy into a temp dir so the real repository's .venv is untouched.
            copy = Path(tmp) / "llm-metrics"
            copy.mkdir()
            shutil.copy2(RUN_SH, copy / "run.sh")
            for name in ("llm_metrics", "tests"):
                shutil.copytree(
                    REPO_ROOT / name,
                    copy / name,
                    ignore=shutil.ignore_patterns("__pycache__"),
                )
            env = {
                k: v
                for k, v in os.environ.items()
                if k not in ("APP_ENV", "LLM_METRICS_DB_PATH")
            }
            env[NESTED] = "1"
            env["LLM_METRICS_PORT"] = "0"  # any free port

            db_path = copy / "data" / "llm_metrics.db"

            def count_rows():
                with closing(sqlite3.connect(db_path)) as conn:
                    return conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]

            # First run: creates .venv, measures, saves, then serves the dashboard.
            _, out, err, page = run_until_dashboard(copy, env)
            self.assertIn("Creating Python environment", out)
            self.assertIn("Tests passed", out)
            self.assertIn("Provider: dummy", out)
            self.assertRegex(out, r"TTFT: \d+\.\d ms")
            self.assertTrue((copy / ".venv" / "bin" / "python").exists())
            self.assertIn("Saved observation to data/llm_metrics.db", out)
            self.assertEqual(count_rows(), 1)
            self.assertRegex(out, r"Dashboard: http://127\.0\.0\.1:\d+/")
            self.assertIsNotNone(page, out + err)
            self.assertIn("TEST / SIMULATED DATA", page)
            self.assertIn("All 1 observations", page)

            # Re-running reuses the existing .venv.
            _, out, err, page = run_until_dashboard(copy, env)
            self.assertNotIn("Creating Python environment", out)
            self.assertIn("TTFT:", out)
            self.assertEqual(count_rows(), 2)
            self.assertIn("All 2 observations", page)

            # A failing test stops the run before the measurement and dashboard.
            (copy / "tests" / "test_zz_fail.py").write_text(
                "import unittest\n"
                "class F(unittest.TestCase):\n"
                "    def test_fail(self):\n"
                "        self.fail('deliberate')\n"
            )
            returncode, out, err, page = run_until_dashboard(copy, env)
            self.assertNotEqual(returncode, 0)
            self.assertIn("Tests failed", err)
            self.assertNotIn("TTFT:", out)
            self.assertIsNone(page)
            self.assertEqual(count_rows(), 2)

            # prod refuses to measure, so the dashboard is not started either.
            (copy / "tests" / "test_zz_fail.py").unlink()
            returncode, out, err, page = run_until_dashboard(copy, {**env, "APP_ENV": "prod"})
            self.assertEqual(returncode, 2)
            self.assertIsNone(page)
            self.assertEqual(count_rows(), 2)

if __name__ == "__main__":
    unittest.main()
