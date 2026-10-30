import os
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from datetime import timedelta
from pathlib import Path

from llm_metrics.seed_history import HISTORY_START, simulated_ttft_history
from llm_metrics.storage import format_timestamp, save_new_observations, save_request

REPO_ROOT = Path(__file__).resolve().parent.parent


def read_rows(db_path):
    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute("SELECT * FROM observations ORDER BY id")]


class SimulatedHistoryTest(unittest.TestCase):
    def test_168_hourly_observations_over_7_days(self):
        history = simulated_ttft_history()
        self.assertEqual(len(history), 168)
        times = [recorded_at for recorded_at, _ in history]
        self.assertEqual(times[0], HISTORY_START)
        self.assertEqual(times[-1] - times[0], timedelta(days=7) - timedelta(hours=1))
        for earlier, later in zip(times, times[1:]):
            self.assertEqual(later - earlier, timedelta(hours=1))

    def test_all_dummy_ttft(self):
        for _, result in simulated_ttft_history():
            self.assertEqual(
                (result["provider"], result["model"], result["metric"]),
                ("dummy", "dummy-model-v1", "ttft"),
            )

    def test_deterministic(self):
        self.assertEqual(simulated_ttft_history(), simulated_ttft_history())

    def test_values_vary_and_include_spikes(self):
        values = [result["value"] for _, result in simulated_ttft_history()]
        self.assertTrue(all(v > 0 for v in values))
        self.assertGreater(len(set(values)), 100)
        median = statistics.median(values)
        spikes = [v for v in values if v > 2 * median]
        self.assertTrue(1 <= len(spikes) <= 10, spikes)


class SeedDatabaseTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db_path = Path(tmp.name) / "data" / "llm_metrics.db"

    def seed(self):
        return save_new_observations(self.db_path, simulated_ttft_history(), "test")

    def test_seeded_rows_have_explicit_historical_timestamps(self):
        self.assertEqual(self.seed(), 168)
        rows = read_rows(self.db_path)
        self.assertEqual(len(rows), 168)
        expected_times = [format_timestamp(t) for t, _ in simulated_ttft_history()]
        self.assertEqual([r["recorded_at"] for r in rows], expected_times)
        self.assertEqual(rows[0]["recorded_at"], "2026-10-23T00:00:00.000000Z")
        for row in rows:
            self.assertEqual(
                (row["environment"], row["provider"], row["model"], row["metric"]),
                ("test", "dummy", "dummy-model-v1", "ttft"),
            )

    def test_reseeding_creates_no_duplicates(self):
        self.seed()
        self.assertEqual(self.seed(), 0)
        self.assertEqual(len(read_rows(self.db_path)), 168)

    def test_live_measurements_still_append(self):
        self.seed()
        live = {"provider": "dummy", "model": "dummy-model-v1", "metric": "ttft", "value": 100.2}
        request = {
            "provider": "dummy", "model": "dummy-model-v1", "input_tokens": 3,
            "requested_max_output_tokens": 64, "output_tokens": 7,
            "input_price_per_1m": 2.0, "output_price_per_1m": 8.0,
            "input_cost": 6e-06, "output_cost": 5.6e-05, "total_cost": 6.2e-05,
        }
        save_request(self.db_path, request, [live], "test")
        save_request(self.db_path, request, [live], "test")
        self.seed()
        self.assertEqual(len(read_rows(self.db_path)), 170)

    def test_seeds_a_database_created_before_the_unique_index(self):
        # Databases from Step 003 have the table but not the unique index.
        self.db_path.parent.mkdir(parents=True)
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute(
                "CREATE TABLE observations (id INTEGER PRIMARY KEY,"
                " recorded_at TEXT NOT NULL, environment TEXT NOT NULL,"
                " provider TEXT NOT NULL, model TEXT NOT NULL,"
                " metric TEXT NOT NULL, value REAL NOT NULL)"
            )
            conn.execute(
                "INSERT INTO observations VALUES"
                " (1, '2026-10-30T00:43:46.279219Z', 'test', 'dummy', 'dummy-model-v1', 'ttft', 100.3)"
            )
        self.assertEqual(self.seed(), 168)
        self.assertEqual(self.seed(), 0)
        self.assertEqual(len(read_rows(self.db_path)), 169)


class SeedCommandTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db_path = Path(tmp.name) / "observations.db"

    def run_seed(self, app_env="test"):
        env = {k: v for k, v in os.environ.items() if k != "APP_ENV"}
        env["APP_ENV"] = app_env
        env["LLM_METRICS_DB_PATH"] = str(self.db_path)
        return subprocess.run(
            [sys.executable, "-m", "llm_metrics.seed_history"],
            cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=30,
        )

    def test_seed_then_reseed(self):
        first = self.run_seed()
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertIn("168 new, 0 already present", first.stdout)
        second = self.run_seed()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("0 new, 168 already present", second.stdout)
        self.assertEqual(len(read_rows(self.db_path)), 168)

    def test_refuses_prod(self):
        proc = self.run_seed("prod")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("APP_ENV=test", proc.stderr)
        self.assertFalse(self.db_path.exists())


if __name__ == "__main__":
    unittest.main()
