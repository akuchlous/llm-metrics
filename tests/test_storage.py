import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from llm_metrics import pricing
from llm_metrics.pricing import price_for, request_cost
from llm_metrics.storage import (
    SCHEMA_VERSION,
    connect,
    load_observations,
    load_recent_requests,
    load_request,
    save_request,
)

DUMMY = {"provider": "dummy", "model": "dummy-model-v1"}
REQUEST = {
    **DUMMY,
    "input_tokens": 3,
    "requested_max_output_tokens": 64,
    "output_tokens": 7,
    "input_price_per_1m": 2.0,
    "output_price_per_1m": 8.0,
    "input_cost": 6e-06,
    "output_cost": 5.6e-05,
    "total_cost": 6.2e-05,
}
RESULTS = [
    {**DUMMY, "metric": "total_latency", "value": 180.0},
    {**DUMMY, "metric": "ttft", "value": 100.0},
    {**DUMMY, "metric": "output_chunks_per_s", "value": 50.0},
]


def init(db_path):
    with closing(connect(db_path)):
        pass


def read_rows(db_path, table="observations"):
    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute(f"SELECT * FROM {table} ORDER BY rowid")]


class StorageTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        # A subdirectory that does not exist yet, like data/ in a fresh clone.
        self.db_path = Path(tmp.name) / "data" / "llm_metrics.db"

    def save(self, request=REQUEST, results=RESULTS, environment="test"):
        return save_request(self.db_path, request, results, environment)

    def test_init_creates_fresh_empty_database(self):
        init(self.db_path)
        self.assertTrue(self.db_path.exists())
        self.assertEqual(read_rows(self.db_path), [])
        self.assertEqual(read_rows(self.db_path, "requests"), [])

    def test_init_is_idempotent_and_keeps_data(self):
        init(self.db_path)
        self.save()
        init(self.db_path)
        self.assertEqual(len(read_rows(self.db_path)), 3)
        self.assertEqual(len(read_rows(self.db_path, "requests")), 1)

    def test_request_and_observations_share_identity_and_timestamp(self):
        before = datetime.now(timezone.utc)
        request_id = self.save()
        after = datetime.now(timezone.utc)

        [request] = read_rows(self.db_path, "requests")
        observations = read_rows(self.db_path)
        self.assertRegex(request_id, r"^[0-9a-f]{32}$")
        self.assertEqual(request["id"], request_id)
        self.assertEqual([o["request_id"] for o in observations], [request_id] * 3)
        self.assertEqual({o["recorded_at"] for o in observations}, {request["recorded_at"]})
        recorded_at = datetime.strptime(
            request["recorded_at"], "%Y-%m-%dT%H:%M:%S.%fZ"
        ).replace(tzinfo=timezone.utc)
        self.assertTrue(before - timedelta(seconds=1) <= recorded_at <= after + timedelta(seconds=1))

    def test_requested_max_and_actual_output_tokens_are_separate(self):
        request_id = self.save({**REQUEST, "requested_max_output_tokens": 64, "output_tokens": 7})
        loaded = load_request(self.db_path, request_id)
        self.assertEqual(loaded["requested_max_output_tokens"], 64)
        self.assertEqual(loaded["output_tokens"], 7)
        self.assertEqual(loaded["input_tokens"], 3)

    def test_load_request_returns_facts_and_metrics_together(self):
        request_id = self.save()
        loaded = load_request(self.db_path, request_id)
        for key, value in REQUEST.items():
            self.assertEqual(loaded[key], value, key)
        self.assertEqual(loaded["environment"], "test")
        self.assertEqual(
            loaded["metrics"], {"total_latency": 180.0, "ttft": 100.0, "output_chunks_per_s": 50.0}
        )
        self.assertIsNone(load_request(self.db_path, "0" * 32))

    def test_request_without_throughput_has_no_fabricated_metric(self):
        request_id = self.save(results=RESULTS[:2])
        self.assertNotIn("output_chunks_per_s", load_request(self.db_path, request_id)["metrics"])

    def test_metric_populations_stay_separate(self):
        self.save()
        start = datetime.now(timezone.utc) - timedelta(minutes=1)
        end = datetime.now(timezone.utc)
        for result in RESULTS:
            loaded = load_observations(
                self.db_path, "test", "dummy", "dummy-model-v1", result["metric"], start=start, end=end
            )
            self.assertEqual([v for _, v in loaded], [result["value"]])

    def test_everything_or_nothing(self):
        bad_observation = [*RESULTS[:2], {**RESULTS[2], "value": None}]  # NOT NULL
        with self.assertRaises(sqlite3.IntegrityError):
            self.save(results=bad_observation)
        bad_request = {**REQUEST, "input_tokens": -1}  # CHECK
        with self.assertRaises(sqlite3.IntegrityError):
            self.save(request=bad_request)
        with self.assertRaises(sqlite3.IntegrityError):
            self.save(environment="staging")  # CHECK
        self.assertEqual(read_rows(self.db_path), [])
        self.assertEqual(read_rows(self.db_path, "requests"), [])

    def test_recent_requests_newest_first_limited_and_filtered(self):
        ids = []
        for i in range(3):
            ids.append(self.save({**REQUEST, "output_tokens": i}))
            time.sleep(0.002)  # distinct timestamps
        self.save(environment="prod")
        recent = load_recent_requests(self.db_path, "test", limit=2)
        self.assertEqual([r["id"] for r in recent], [ids[2], ids[1]])
        self.assertEqual(recent[0]["metrics"]["total_latency"], 180.0)
        self.assertEqual(len(load_recent_requests(self.db_path, "prod", limit=20)), 1)

    def test_pricing_basis_survives_a_price_change(self):
        price = price_for("dummy", "dummy-model-v1")
        cost = request_cost(3, 7, price)
        request = {
            **REQUEST,
            "input_price_per_1m": price.input_per_1m,
            "output_price_per_1m": price.output_per_1m,
            **cost,
        }
        request_id = self.save(request)
        new_price = pricing.Price(input_per_1m=99.0, output_per_1m=999.0)
        with mock.patch.dict(pricing.PRICES, {("dummy", "dummy-model-v1"): new_price}):
            self.assertEqual(price_for("dummy", "dummy-model-v1"), new_price)
            loaded = load_request(self.db_path, request_id)
        self.assertEqual((loaded["input_price_per_1m"], loaded["output_price_per_1m"]), (2.0, 8.0))
        self.assertEqual(loaded["total_cost"], cost["total_cost"])
        # The stored rates alone explain the stored cost.
        recomputed = request_cost(
            loaded["input_tokens"], loaded["output_tokens"],
            pricing.Price(loaded["input_price_per_1m"], loaded["output_price_per_1m"]),
        )
        self.assertEqual(recomputed["total_cost"], loaded["total_cost"])

    def test_values_are_stored_literally_not_as_sql(self):
        hostile = "x'); DROP TABLE observations; --"
        request_id = self.save({**REQUEST, "provider": hostile},
                               [{**RESULTS[0], "provider": hostile}])
        self.assertEqual(load_request(self.db_path, request_id)["provider"], hostile)
        self.assertEqual(read_rows(self.db_path)[0]["provider"], hostile)


OLD_OBSERVATIONS_V0 = (
    "CREATE TABLE observations (id INTEGER PRIMARY KEY, recorded_at TEXT NOT NULL,"
    " environment TEXT NOT NULL CHECK (environment IN ('test', 'prod')),"
    " provider TEXT NOT NULL, model TEXT NOT NULL, metric TEXT NOT NULL,"
    " value_ms REAL NOT NULL)"
)
OLD_ROW = (
    "INSERT INTO observations VALUES"
    " (1, '2026-10-30T00:43:46.279219Z', 'test', 'dummy', 'dummy-model-v1', 'ttft', 100.3)"
)


class SchemaUpgradeTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db_path = Path(tmp.name) / "llm_metrics.db"

    def version(self):
        with closing(sqlite3.connect(self.db_path)) as conn:
            return conn.execute("PRAGMA user_version").fetchone()[0]

    def make_old(self, create_sql, version):
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.execute(create_sql)
            conn.execute(OLD_ROW)
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(f"PRAGMA user_version = {version}")

    def assert_old_row_kept_without_fabrication(self):
        self.assertEqual(self.version(), SCHEMA_VERSION)
        rows = read_rows(self.db_path)
        self.assertEqual(
            [(r["metric"], r["value"], r["request_id"]) for r in rows], [("ttft", 100.3, None)]
        )
        self.assertNotIn("value_ms", rows[0])
        self.assertEqual(read_rows(self.db_path, "requests"), [])  # no invented requests
        # New requests still work after the upgrade, and re-upgrading is a no-op.
        save_request(self.db_path, REQUEST, RESULTS, "test")
        init(self.db_path)
        self.assertEqual(len(read_rows(self.db_path)), 4)

    def test_fresh_database_is_current_version(self):
        init(self.db_path)
        self.assertEqual(self.version(), SCHEMA_VERSION)
        self.assertEqual(SCHEMA_VERSION, 2)

    def test_version_0_database_is_upgraded(self):
        self.make_old(OLD_OBSERVATIONS_V0, 0)
        init(self.db_path)
        self.assert_old_row_kept_without_fabrication()

    def test_version_1_database_is_upgraded(self):
        self.make_old(OLD_OBSERVATIONS_V0.replace("value_ms", "value"), 1)
        init(self.db_path)
        self.assert_old_row_kept_without_fabrication()

    def test_newer_database_is_refused(self):
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
        with self.assertRaisesRegex(RuntimeError, "newer than this code"):
            connect(self.db_path)


if __name__ == "__main__":
    unittest.main()
