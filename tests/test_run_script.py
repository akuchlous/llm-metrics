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

            # prod on a fresh copy: never seeds, refuses to measure, no dashboard.
            returncode, out, err, page = run_until_dashboard(copy, {**env, "APP_ENV": "prod"})
            self.assertEqual(returncode, 2)
            self.assertIn("Creating Python environment", out)
            self.assertNotIn("Simulated history", out)
            self.assertIsNone(page)
            self.assertFalse(db_path.exists())

            # First test-mode run: seeds 168 rows, saves 3 metrics, serves the dashboard.
            _, out, err, page = run_until_dashboard(copy, env)
            self.assertNotIn("Creating Python environment", out)  # .venv reused
            self.assertIn("Tests passed", out)
            self.assertIn("168 new, 0 already present", out)
            self.assertIn("Provider: dummy", out)
            self.assertRegex(out, r"TTFT: \d+\.\d ms")
            self.assertRegex(out, r"Total latency: \d+\.\d ms")
            self.assertRegex(out, r"Output throughput: \d+\.\d chunks/s")
            self.assertIn("Saved 3 observations to data/llm_metrics.db", out)
            self.assertEqual(count_rows(), 171)
            self.assertRegex(out, r"Dashboard: http://127\.0\.0\.1:\d+/")
            self.assertIsNotNone(page, out + err)
            self.assertIn("TEST / SIMULATED DATA", page)
            # How much seeded history falls in the default 7d window depends on
            # today's date; the live row just measured is always in it.
            self.assertIn('href="/?window=7d&amp;metric=ttft" aria-current="page"', page)
            self.assertRegex(page, r"\d+ observations? in window")
            self.assertIn("p99", page)

            # Second run: history already present, only the three live rows are added.
            _, out, err, page = run_until_dashboard(copy, env)
            self.assertIn("0 new, 168 already present", out)
            self.assertEqual(count_rows(), 174)
            self.assertRegex(page, r"\d+ observations? in window")

            # A failing test stops the run before seeding, measuring, or serving.
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
            self.assertEqual(count_rows(), 174)


if __name__ == "__main__":
    unittest.main()
