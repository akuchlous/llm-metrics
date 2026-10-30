import os
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUN_SH = REPO_ROOT / "run.sh"

# run.sh runs the whole test suite, which includes this file. The end-to-end test
# sets this variable when it calls run.sh so the nested run skips it (no recursion).
NESTED = "LLM_METRICS_INSIDE_RUN_SH_TEST"


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

            db_path = copy / "data" / "llm_metrics.db"

            def count_rows():
                with closing(sqlite3.connect(db_path)) as conn:
                    return conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]

            def run():
                return subprocess.run(
                    ["./run.sh"], cwd=copy, env=env,
                    capture_output=True, text=True, timeout=120,
                )

            first = run()
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            self.assertIn("Creating Python environment", first.stdout)
            self.assertIn("Tests passed", first.stdout)
            self.assertIn("Provider: dummy", first.stdout)
            self.assertRegex(first.stdout, r"TTFT: \d+\.\d ms")
            self.assertTrue((copy / ".venv" / "bin" / "python").exists())
            self.assertIn("Saved observation to data/llm_metrics.db", first.stdout)
            self.assertEqual(count_rows(), 1)

            # Re-running reuses the existing .venv.
            second = run()
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            self.assertNotIn("Creating Python environment", second.stdout)
            self.assertIn("TTFT:", second.stdout)
            self.assertEqual(count_rows(), 2)

            # A failing test stops the run before the measurement.
            (copy / "tests" / "test_zz_fail.py").write_text(
                "import unittest\n"
                "class F(unittest.TestCase):\n"
                "    def test_fail(self):\n"
                "        self.fail('deliberate')\n"
            )
            failed = run()
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("Tests failed", failed.stderr)
            self.assertNotIn("TTFT:", failed.stdout)
            self.assertEqual(count_rows(), 2)


if __name__ == "__main__":
    unittest.main()
