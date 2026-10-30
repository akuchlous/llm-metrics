import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from llm_metrics.storage import SCHEMA_VERSION, connect, load_observations, save_observations

RESULT = {"provider": "dummy", "model": "dummy-model-v1", "metric": "ttft", "value": 100.4}


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
        self.assertAlmostEqual(row["value"], 100.4)

        self.assertTrue(row["recorded_at"].endswith("Z"))
        recorded_at = datetime.strptime(
            row["recorded_at"], "%Y-%m-%dT%H:%M:%S.%fZ"
        ).replace(tzinfo=timezone.utc)
        tolerance = timedelta(seconds=1)
        self.assertTrue(before - tolerance <= recorded_at <= after + tolerance)

    def test_multiple_observations_are_appended(self):
        for value in (10.0, 20.0, 30.0):
            save_observations(self.db_path, [{**RESULT, "value": value}], "test")
        rows = read_rows(self.db_path)
        self.assertEqual([r["value"] for r in rows], [10.0, 20.0, 30.0])
        self.assertEqual(len({r["id"] for r in rows}), 3)

    def test_unknown_environment_is_rejected(self):
        with self.assertRaises(sqlite3.IntegrityError):
            save_observations(self.db_path, [RESULT], "staging")
        self.assertEqual(read_rows(self.db_path), [])

    def test_metrics_from_one_request_share_a_timestamp_and_stay_separate(self):
        ttft = {**RESULT, "metric": "ttft", "value": 100.0}
        total = {**RESULT, "metric": "total_latency", "value": 180.0}
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

    def test_three_metrics_saved_atomically_and_queried_separately(self):
        results = [
            {**RESULT, "metric": "ttft", "value": 100.0},
            {**RESULT, "metric": "total_latency", "value": 180.0},
            {**RESULT, "metric": "output_chunks_per_s", "value": 50.0},
        ]
        save_observations(self.db_path, results, "test")
        rows = read_rows(self.db_path)
        self.assertEqual(len(rows), 3)
        self.assertEqual(len({r["recorded_at"] for r in rows}), 1)
        start = datetime.now(timezone.utc) - timedelta(minutes=1)
        end = datetime.now(timezone.utc)
        for result in results:
            loaded = load_observations(
                self.db_path, "test", "dummy", "dummy-model-v1", result["metric"], start=start, end=end
            )
            self.assertEqual([v for _, v in loaded], [result["value"]])

        bad = [*results[:2], {**results[2], "value": None}]  # third row violates NOT NULL
        with self.assertRaises(sqlite3.IntegrityError):
            save_observations(self.db_path, bad, "test")
        self.assertEqual(len(read_rows(self.db_path)), 3)  # nothing from the failed batch

    def test_batch_is_all_or_nothing(self):
        bad = {**RESULT, "metric": "total_latency", "value": None}  # violates NOT NULL
        with self.assertRaises(sqlite3.IntegrityError):
            save_observations(self.db_path, [RESULT, bad], "test")
        self.assertEqual(read_rows(self.db_path), [])

    def test_values_are_stored_literally_not_as_sql(self):
        hostile = "x'); DROP TABLE observations; --"
        save_observations(self.db_path, [{**RESULT, "provider": hostile}], "test")
        [row] = read_rows(self.db_path)
        self.assertEqual(row["provider"], hostile)


class SchemaUpgradeTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db_path = Path(tmp.name) / "llm_metrics.db"

    def version(self):
        with closing(sqlite3.connect(self.db_path)) as conn:
            return conn.execute("PRAGMA user_version").fetchone()[0]

    def test_fresh_database_is_current_version(self):
        with closing(connect(self.db_path)):
            pass
        self.assertEqual(self.version(), SCHEMA_VERSION)
        self.assertEqual(read_rows(self.db_path), [])

    def test_version_0_database_is_upgraded_and_keeps_rows(self):
        # A database as created by Steps 003-008: `value_ms` column, user_version 0.
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute(
                "CREATE TABLE observations (id INTEGER PRIMARY KEY, recorded_at TEXT NOT NULL,"
                " environment TEXT NOT NULL CHECK (environment IN ('test', 'prod')),"
                " provider TEXT NOT NULL, model TEXT NOT NULL, metric TEXT NOT NULL,"
                " value_ms REAL NOT NULL)"
            )
            conn.execute(
                "INSERT INTO observations VALUES"
                " (1, '2026-10-30T00:43:46.279219Z', 'test', 'dummy', 'dummy-model-v1', 'ttft', 100.3)"
            )
        save_observations(self.db_path, [{**RESULT, "metric": "output_chunks_per_s", "value": 50.0}], "test")
        self.assertEqual(self.version(), 1)
        rows = read_rows(self.db_path)
        self.assertEqual([(r["metric"], r["value"]) for r in rows],
                         [("ttft", 100.3), ("output_chunks_per_s", 50.0)])
        self.assertNotIn("value_ms", rows[0])
        # Upgrading again is a no-op.
        with closing(connect(self.db_path)):
            pass
        self.assertEqual(len(read_rows(self.db_path)), 2)

    def test_newer_database_is_refused(self):
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
        with self.assertRaisesRegex(RuntimeError, "newer than this code"):
            connect(self.db_path)


if __name__ == "__main__":
    unittest.main()
