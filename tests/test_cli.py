"""Tests for the simulated CLI (`python -m llm_metrics`).

Each test uses a temporary database via LLM_METRICS_DB_PATH, so the
developer's database is never written. The CLI never makes network calls.
"""

import contextlib
import io
import os
import pathlib
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from llm_metrics import __main__ as cli
from llm_metrics import providers

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


class CLITest(unittest.TestCase):
    extra_env = {}

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        # Never write to the developer's real database.
        self.db_path = pathlib.Path(tmp.name) / "observations.db"

    def run_cli(self, app_env):
        env = {
            k: v
            for k, v in os.environ.items()
            if k != "APP_ENV" and not k.startswith("LLM_METRICS_ORIGIN_")
        }
        env["LLM_METRICS_DB_PATH"] = str(self.db_path)
        env.update(self.extra_env)
        if app_env is not None:
            env["APP_ENV"] = app_env
        return subprocess.run(
            [sys.executable, "-m", "llm_metrics"],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

    def test_test_env_prints_all_metrics_with_units(self):
        proc = self.run_cli("test")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Provider: dummy", proc.stdout)
        self.assertIn("Model: dummy-model-v1", proc.stdout)
        self.assertRegex(proc.stdout, r"TTFT: \d+\.\d ms")
        self.assertRegex(proc.stdout, r"Total latency: \d+\.\d ms")
        self.assertRegex(
            proc.stdout, r"Output token throughput: \d+\.\d tokens/s"
        )
        self.assertRegex(
            proc.stdout, r"Output chunk throughput: \d+\.\d chunks/s"
        )
        self.assertIn("Workload: simulated.default.v1", proc.stdout)
        self.assertIn("Origin: local / unknown", proc.stdout)
        # The simulated provider sends no cache control and reports no cached
        # tokens.
        self.assertIn("Cache policy: provider_default", proc.stdout)
        self.assertIn("Cached input tokens: not reported", proc.stdout)

    def test_workload_and_origin_are_saved(self):
        self.extra_env = {
            "LLM_METRICS_ORIGIN_CLOUD": "aws",
            "LLM_METRICS_ORIGIN_REGION": "us-east-1",
        }
        proc = self.run_cli("test")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Origin: aws / us-east-1", proc.stdout)
        with contextlib.closing(sqlite3.connect(self.db_path)) as conn:
            rows = conn.execute(
                "SELECT workload_id, origin_cloud, origin_region, cache_policy,"
                " cached_input_tokens FROM requests"
            ).fetchall()
        self.assertEqual(
            rows,
            [
                (
                    "simulated.default.v1",
                    "aws",
                    "us-east-1",
                    "provider_default",
                    None,
                )
            ],
        )

    def test_invalid_origin_is_refused_before_measuring(self):
        self.extra_env = {"LLM_METRICS_ORIGIN_REGION": "US East 1"}
        proc = self.run_cli("test")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("Invalid LLM_METRICS_ORIGIN_REGION", proc.stderr)
        self.assertNotIn("US East 1", proc.stderr)  # input is not echoed
        self.assertFalse(self.db_path.exists())

    def test_test_env_saves_one_request_with_all_metrics(self):
        proc = self.run_cli("test")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Outcome: success", proc.stdout)
        self.assertRegex(
            proc.stdout, r"Saved attempt [0-9a-f]{32} with 4 observations to"
        )
        self.assertIn("Input tokens: 3 (simulated)", proc.stdout)
        self.assertIn("Output tokens: 7 of max 64 (simulated)", proc.stdout)
        self.assertIn(
            "Cost: $0.000062 (input $0.000006 + output $0.000056) (simulated)",
            proc.stdout,
        )
        with contextlib.closing(sqlite3.connect(self.db_path)) as conn:
            [request] = conn.execute(
                "SELECT id, recorded_at, environment, input_tokens,"
                " requested_max_output_tokens,"
                " output_tokens, input_price_per_1m, output_price_per_1m,"
                " total_cost FROM requests"
                " WHERE outcome = 'success' AND failed_after_ms IS NULL"
            ).fetchall()
            rows = conn.execute(
                "SELECT recorded_at, environment, provider, model, metric,"
                " value, request_id"
                " FROM observations ORDER BY id"
            ).fetchall()
        request_id, recorded_at, environment, *facts = request
        self.assertEqual(environment, "test")
        self.assertEqual(facts[:5], [3, 64, 7, 2.0, 8.0])
        self.assertAlmostEqual(facts[5], 6.2e-05, places=15)
        self.assertEqual(
            [r[4] for r in rows],
            [
                "total_latency",
                "ttft",
                "output_tokens_per_s",
                "output_chunks_per_s",
            ],
        )
        for (
            row_recorded_at,
            row_env,
            provider,
            model,
            _,
            value,
            row_request,
        ) in rows:
            self.assertEqual(
                (row_env, provider, model), ("test", "dummy", "dummy-model-v1")
            )
            self.assertEqual(
                (row_recorded_at, row_request), (recorded_at, request_id)
            )
            self.assertGreater(value, 0)
        self.assertGreaterEqual(rows[0][5], rows[1][5])  # total >= TTFT

    def test_failed_attempt_is_recorded_in_process(self):
        # The normal CLI path never fails; inject a failing dummy provider.
        provider = providers.DummyProvider(
            first_token_delay_s=0,
            inter_token_delay_s=0,
            fail_with="provider_error",
            fail_after_chunks=2,
        )
        out = io.StringIO()
        with mock.patch.dict(
            os.environ,
            {"LLM_METRICS_DB_PATH": str(self.db_path), "APP_ENV": "test"},
        ), mock.patch.object(
            cli.config, "get_provider", return_value=provider
        ), contextlib.redirect_stdout(
            out
        ):
            self.assertEqual(
                cli.main(), 0
            )  # a failed attempt is a recorded result
        text = out.getvalue()
        self.assertIn(
            "Outcome: FAILED — Provider/server error (provider_error)", text
        )
        self.assertIn("unknown (not recorded)", text)
        self.assertNotIn(
            "simulated failure", text
        )  # provider message never shown or stored
        with contextlib.closing(sqlite3.connect(self.db_path)) as conn:
            [row] = conn.execute(
                "SELECT outcome, input_tokens, output_tokens, total_cost,"
                " failed_after_ms,"
                " requested_max_output_tokens FROM requests"
            ).fetchall()
            observations = conn.execute(
                "SELECT COUNT(*) FROM observations"
            ).fetchone()[0]
        self.assertEqual(row[:4], ("provider_error", None, None, None))
        self.assertGreaterEqual(row[4], 0)
        self.assertEqual(row[5], 64)
        self.assertEqual(observations, 0)

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
