import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from llm_metrics.storage import connect, load_observations, save_observations

RESULT = {"provider": "dummy", "model": "dummy-model-v1", "metric": "ttft", "value_ms": 100.4}


def init(db_path):
    with closing(connect(db_path)):
        pass


def read_rows(db_path):
    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute("SELECT * FROM observations ORDER BY id")]


class StorageTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        # A subdirectory that does not exist yet, like data/ in a fresh clone.
        self.db_path = Path(tmp.name) / "data" / "llm_metrics.db"

    def test_init_creates_fresh_empty_database(self):
        init(self.db_path)
        self.assertTrue(self.db_path.exists())
        self.assertEqual(read_rows(self.db_path), [])

    def test_init_is_idempotent_and_keeps_data(self):
        init(self.db_path)
        save_observations(self.db_path, [RESULT], "test")
        init(self.db_path)
        self.assertEqual(len(read_rows(self.db_path)), 1)

    def test_saved_observation_fields(self):
        before = datetime.now(timezone.utc)
        save_observations(self.db_path, [RESULT], "test")
        after = datetime.now(timezone.utc)

        [row] = read_rows(self.db_path)
        self.assertIsInstance(row["id"], int)
        self.assertEqual(row["environment"], "test")
        self.assertEqual(row["provider"], "dummy")
        self.assertEqual(row["model"], "dummy-model-v1")
        self.assertEqual(row["metric"], "ttft")
        self.assertAlmostEqual(row["value_ms"], 100.4)

        self.assertTrue(row["recorded_at"].endswith("Z"))
        recorded_at = datetime.strptime(
            row["recorded_at"], "%Y-%m-%dT%H:%M:%S.%fZ"
        ).replace(tzinfo=timezone.utc)
        tolerance = timedelta(seconds=1)
        self.assertTrue(before - tolerance <= recorded_at <= after + tolerance)

    def test_multiple_observations_are_appended(self):
        for value in (10.0, 20.0, 30.0):
            save_observations(self.db_path, [{**RESULT, "value_ms": value}], "test")
        rows = read_rows(self.db_path)
        self.assertEqual([r["value_ms"] for r in rows], [10.0, 20.0, 30.0])
        self.assertEqual(len({r["id"] for r in rows}), 3)

    def test_unknown_environment_is_rejected(self):
        with self.assertRaises(sqlite3.IntegrityError):
            save_observations(self.db_path, [RESULT], "staging")
        self.assertEqual(read_rows(self.db_path), [])

    def test_metrics_from_one_request_share_a_timestamp_and_stay_separate(self):
        ttft = {**RESULT, "metric": "ttft", "value_ms": 100.0}
        total = {**RESULT, "metric": "total_latency", "value_ms": 180.0}
        save_observations(self.db_path, [ttft, total], "test")
        rows = read_rows(self.db_path)
        self.assertEqual([r["metric"] for r in rows], ["ttft", "total_latency"])
        self.assertEqual(rows[0]["recorded_at"], rows[1]["recorded_at"])

        start = datetime.now(timezone.utc) - timedelta(minutes=1)
        end = datetime.now(timezone.utc)
        for metric, value in (("ttft", 100.0), ("total_latency", 180.0)):
            loaded = load_observations(
                self.db_path, "test", "dummy", "dummy-model-v1", metric, start=start, end=end
            )
            self.assertEqual([v for _, v in loaded], [value])

    def test_batch_is_all_or_nothing(self):
        bad = {**RESULT, "metric": "total_latency", "value_ms": None}  # violates NOT NULL
        with self.assertRaises(sqlite3.IntegrityError):
            save_observations(self.db_path, [RESULT, bad], "test")
        self.assertEqual(read_rows(self.db_path), [])

    def test_values_are_stored_literally_not_as_sql(self):
        hostile = "x'); DROP TABLE observations; --"
        save_observations(self.db_path, [{**RESULT, "provider": hostile}], "test")
        [row] = read_rows(self.db_path)
        self.assertEqual(row["provider"], hostile)


if __name__ == "__main__":
    unittest.main()
