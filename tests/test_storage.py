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
    count_outcomes,
    load_observations,
    load_recent_requests,
    load_request,
    save_request,
    spend_by_model,
)

DUMMY = {"provider": "dummy", "model": "dummy-model-v1"}
# Request facts every new attempt must supply (Step 013).
NEW_FACTS = {"workload_id": "simulated.default.v1", "origin_cloud": "local", "origin_region": "unknown"}
REQUEST = {
    **DUMMY,
    **NEW_FACTS,
    "input_tokens": 3,
    "requested_max_output_tokens": 64,
    "output_tokens": 7,
    "input_price_per_1m": 2.0,
    "output_price_per_1m": 8.0,
    "input_cost": 6e-06,
    "output_cost": 5.6e-05,
    "total_cost": 6.2e-05,
    "outcome": "success",
    "failed_after_ms": None,
}
FAILED = {
    **DUMMY,
    **NEW_FACTS,
    "outcome": "rate_limited",
    "input_tokens": None,
    "requested_max_output_tokens": 64,
    "output_tokens": None,
    "input_price_per_1m": 2.0,
    "output_price_per_1m": 8.0,
    "input_cost": None,
    "output_cost": None,
    "total_cost": None,
    "failed_after_ms": 12.5,
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

    def test_failed_attempt_is_persisted_with_unknown_facts(self):
        request_id = self.save(FAILED, results=[])
        loaded = load_request(self.db_path, request_id)
        self.assertEqual(loaded["outcome"], "rate_limited")
        self.assertEqual(loaded["failed_after_ms"], 12.5)
        for unknown in ("input_tokens", "output_tokens", "input_cost", "output_cost", "total_cost"):
            self.assertIsNone(loaded[unknown], unknown)  # NULL, not 0
        self.assertEqual(loaded["requested_max_output_tokens"], 64)
        self.assertEqual(loaded["metrics"], {})
        self.assertEqual(read_rows(self.db_path), [])  # no observations at all

    def test_outcome_and_facts_must_be_consistent(self):
        fabricated = {**FAILED, "input_tokens": 0, "output_tokens": 0,
                      "input_cost": 0.0, "output_cost": 0.0, "total_cost": 0.0}
        missing_cost = {**REQUEST, "total_cost": None}
        success_with_failure_time = {**REQUEST, "failed_after_ms": 5.0}
        failure_without_time = {**FAILED, "failed_after_ms": None}
        unknown_outcome = {**FAILED, "outcome": "http_503"}
        for bad in (fabricated, missing_cost, success_with_failure_time,
                    failure_without_time, unknown_outcome):
            with self.subTest(bad=bad):
                with self.assertRaises(sqlite3.IntegrityError):
                    self.save(bad, results=[])
        self.assertEqual(read_rows(self.db_path, "requests"), [])

    def test_new_attempts_must_have_workload_and_origin(self):
        for fact in ("workload_id", "origin_cloud", "origin_region"):
            for bad in (None, ""):
                with self.subTest(fact=fact, value=bad):
                    with self.assertRaisesRegex(ValueError, fact):
                        self.save({**REQUEST, fact: bad})
                    missing = {k: v for k, v in REQUEST.items() if k != fact}
                    with self.assertRaisesRegex(ValueError, fact):
                        self.save(missing)
        self.assertFalse(self.db_path.exists() and read_rows(self.db_path, "requests"))

    def test_failed_attempt_with_metrics_is_refused_before_writing(self):
        with self.assertRaises(ValueError):
            self.save(FAILED, results=RESULTS)
        self.assertFalse(self.db_path.exists())  # refused before opening the database

    def test_count_outcomes_over_all_attempts_in_window(self):
        for request in (REQUEST, REQUEST, FAILED, {**FAILED, "outcome": "timeout"}, FAILED):
            self.save(request, results=RESULTS if request["outcome"] == "success" else [])
        self.save(FAILED, results=[], environment="prod")  # other environment
        now = datetime.now(timezone.utc)
        counts = count_outcomes(self.db_path, "test", "dummy", "dummy-model-v1",
                                start=now - timedelta(minutes=1), end=now)
        self.assertEqual(counts, {"success": 2, "rate_limited": 2, "timeout": 1})
        later = count_outcomes(self.db_path, "test", "dummy", "dummy-model-v1",
                               start=now + timedelta(minutes=1), end=now + timedelta(minutes=2))
        self.assertEqual(later, {})

    def test_failures_do_not_enter_metric_populations(self):
        self.save()
        self.save(FAILED, results=[])
        start = datetime.now(timezone.utc) - timedelta(minutes=1)
        end = datetime.now(timezone.utc)
        for metric in ("total_latency", "ttft", "output_chunks_per_s"):
            loaded = load_observations(self.db_path, "test", "dummy", "dummy-model-v1", metric,
                                       start=start, end=end)
            self.assertEqual(len(loaded), 1, metric)  # only the successful attempt

    def test_values_are_stored_literally_not_as_sql(self):
        hostile = "x'); DROP TABLE observations; --"
        request_id = self.save({**REQUEST, "provider": hostile},
                               [{**RESULTS[0], "provider": hostile}])
        self.assertEqual(load_request(self.db_path, request_id)["provider"], hostile)
        self.assertEqual(read_rows(self.db_path)[0]["provider"], hostile)


def real_request(model="gpt-6-luna", provider="openai", input_tokens=20, output_tokens=15, **overrides):
    price = {"input_price_per_1m": 0.10, "output_price_per_1m": 0.50}
    cost = request_cost(input_tokens, output_tokens, pricing.Price(0.10, 0.50))
    return {**DUMMY, **NEW_FACTS, "provider": provider, "model": model, "outcome": "success",
            "input_tokens": input_tokens, "requested_max_output_tokens": 64,
            "output_tokens": output_tokens, **price, **cost, "failed_after_ms": None, **overrides}


def real_failure(model="gpt-6-luna", provider="openai", category="timeout"):
    return real_request(model, provider, outcome=category, input_cost=None, output_cost=None,
                        total_cost=None, failed_after_ms=9.0) | {"input_tokens": None, "output_tokens": None}


class SpendTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db_path = Path(tmp.name) / "x.db"

    def save(self, request, environment="prod"):
        save_request(self.db_path, request, [], environment)

    def spend(self, environment="prod", minutes=1):
        now = datetime.now(timezone.utc)
        return spend_by_model(self.db_path, environment,
                              start=now - timedelta(minutes=minutes), end=now)

    def test_grouped_by_provider_and_model_from_stored_costs(self):
        self.save(real_request(input_tokens=20, output_tokens=15))   # 9.5e-6
        self.save(real_request(input_tokens=40, output_tokens=30))   # 1.9e-5
        self.save(real_request(model="other-model", input_tokens=10, output_tokens=10))  # 6e-6
        self.save(real_failure())
        rows = {(r["provider"], r["model"]): r for r in self.spend()}
        luna = rows[("openai", "gpt-6-luna")]
        self.assertEqual((luna["attempts"], luna["successful_calls"], luna["failed_attempts"]), (3, 2, 1))
        self.assertEqual((luna["input_tokens"], luna["output_tokens"]), (60, 45))
        self.assertAlmostEqual(luna["total_cost"], 0.0000285, places=15)
        self.assertAlmostEqual(rows[("openai", "other-model")]["total_cost"], 0.000006, places=15)
        self.assertEqual([r["model"] for r in self.spend()], ["gpt-6-luna", "other-model"])  # costliest first

    def test_failure_only_group_has_unknown_cost_not_zero(self):
        self.save(real_failure(model="flaky-model"))
        [row] = self.spend()
        self.assertEqual((row["successful_calls"], row["failed_attempts"]), (0, 1))
        self.assertIsNone(row["total_cost"])
        self.assertIsNone(row["input_tokens"])

    def test_simulated_costs_are_excluded(self):
        self.save(REQUEST, environment="test")  # dummy, simulated cost 6.2e-5
        self.assertEqual(self.spend(), [])
        self.save(real_request())
        [row] = self.spend()
        self.assertEqual(row["provider"], "openai")

    def test_window_filters_attempts(self):
        self.save(real_request())
        now = datetime.now(timezone.utc)
        self.assertEqual(spend_by_model(self.db_path, "prod", start=now + timedelta(minutes=1),
                                        end=now + timedelta(minutes=2)), [])


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


STEP_010_SCHEMA = """
CREATE TABLE requests (
    id TEXT PRIMARY KEY, recorded_at TEXT NOT NULL,
    environment TEXT NOT NULL CHECK (environment IN ('test', 'prod')),
    provider TEXT NOT NULL, model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL CHECK (input_tokens >= 0),
    requested_max_output_tokens INTEGER NOT NULL CHECK (requested_max_output_tokens >= 1),
    output_tokens INTEGER NOT NULL CHECK (output_tokens >= 0),
    input_price_per_1m REAL NOT NULL CHECK (input_price_per_1m >= 0),
    output_price_per_1m REAL NOT NULL CHECK (output_price_per_1m >= 0),
    input_cost REAL NOT NULL, output_cost REAL NOT NULL, total_cost REAL NOT NULL
);
CREATE TABLE observations (
    id INTEGER PRIMARY KEY, recorded_at TEXT NOT NULL,
    environment TEXT NOT NULL CHECK (environment IN ('test', 'prod')),
    provider TEXT NOT NULL, model TEXT NOT NULL, metric TEXT NOT NULL,
    value REAL NOT NULL, request_id TEXT REFERENCES requests (id)
);
CREATE UNIQUE INDEX observations_unique
    ON observations (recorded_at, environment, provider, model, metric);
CREATE INDEX observations_request ON observations (request_id);
"""

STEP_011_REQUESTS = """
CREATE TABLE requests (
    id TEXT PRIMARY KEY, recorded_at TEXT NOT NULL,
    environment TEXT NOT NULL CHECK (environment IN ('test', 'prod')),
    provider TEXT NOT NULL, model TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN (
        'success', 'timeout', 'rate_limited', 'provider_error',
        'transport_error', 'invalid_response')),
    input_tokens INTEGER CHECK (input_tokens >= 0),
    requested_max_output_tokens INTEGER NOT NULL CHECK (requested_max_output_tokens >= 1),
    output_tokens INTEGER CHECK (output_tokens >= 0),
    input_price_per_1m REAL NOT NULL CHECK (input_price_per_1m >= 0),
    output_price_per_1m REAL NOT NULL CHECK (output_price_per_1m >= 0),
    input_cost REAL, output_cost REAL, total_cost REAL,
    failed_after_ms REAL CHECK (failed_after_ms >= 0),
    CHECK (
        (outcome = 'success'
            AND input_tokens IS NOT NULL AND output_tokens IS NOT NULL
            AND input_cost IS NOT NULL AND output_cost IS NOT NULL
            AND total_cost IS NOT NULL AND failed_after_ms IS NULL)
        OR
        (outcome <> 'success'
            AND input_tokens IS NULL AND output_tokens IS NULL
            AND input_cost IS NULL AND output_cost IS NULL
            AND total_cost IS NULL AND failed_after_ms IS NOT NULL)
    )
);
"""


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
        self.assertEqual(SCHEMA_VERSION, 5)

    def test_version_2_requests_become_historical_successes(self):
        # A database exactly as Step 010 created it: NOT NULL token/cost columns,
        # no outcome; one request with linked observations, one unpaired row.
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.executescript(STEP_010_SCHEMA)
            conn.execute(
                "INSERT INTO requests VALUES ('abc', '2026-10-30T05:59:00.000000Z', 'test',"
                " 'dummy', 'dummy-model-v1', 3, 64, 7, 2.0, 8.0, 6e-06, 5.6e-05, 6.2e-05)"
            )
            conn.execute(
                "INSERT INTO observations VALUES (1, '2026-10-30T05:59:00.000000Z', 'test',"
                " 'dummy', 'dummy-model-v1', 'total_latency', 181.1, 'abc')"
            )
            conn.execute(
                "INSERT INTO observations VALUES (2, '2026-10-23T00:00:00.000000Z', 'test',"
                " 'dummy', 'dummy-model-v1', 'ttft', 101.7, NULL)"
            )
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute("PRAGMA user_version = 2")
        init(self.db_path)
        self.assertEqual(self.version(), SCHEMA_VERSION)
        loaded = load_request(self.db_path, "abc")
        self.assertEqual(loaded["outcome"], "success")
        self.assertIsNone(loaded["failed_after_ms"])
        self.assertEqual(
            [loaded[k] for k in ("input_tokens", "requested_max_output_tokens", "output_tokens",
                                 "input_price_per_1m", "output_price_per_1m", "total_cost")],
            [3, 64, 7, 2.0, 8.0, 6.2e-05],
        )
        self.assertEqual(loaded["metrics"], {"total_latency": 181.1})
        rows = read_rows(self.db_path)
        self.assertEqual([(r["metric"], r["request_id"]) for r in rows],
                         [("total_latency", "abc"), ("ttft", None)])  # unpaired row unchanged
        self.assertEqual(len(read_rows(self.db_path, "requests")), 1)  # no attempts invented
        # The upgraded table accepts failures (nullable facts) and is not upgraded twice.
        save_request(self.db_path, FAILED, [], "test")
        init(self.db_path)
        self.assertEqual(len(read_rows(self.db_path, "requests")), 2)

    def test_version_0_database_is_upgraded(self):
        self.make_old(OLD_OBSERVATIONS_V0, 0)
        init(self.db_path)
        self.assert_old_row_kept_without_fabrication()

    def test_version_1_database_is_upgraded(self):
        self.make_old(OLD_OBSERVATIONS_V0.replace("value_ms", "value"), 1)
        init(self.db_path)
        self.assert_old_row_kept_without_fabrication()

    def test_version_3_requests_keep_rows_and_gain_null_provider_request_id(self):
        # The requests table exactly as Step 011 (version 3) created it.
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.executescript(STEP_011_REQUESTS)
            conn.execute(
                "INSERT INTO requests VALUES ('old', '2026-10-30T06:56:16.000000Z', 'prod',"
                " 'openai', 'gpt-6-luna', 'provider_error', NULL, 64, NULL, 0.1, 0.5,"
                " NULL, NULL, NULL, 5425.6)"
            )
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute("PRAGMA user_version = 3")
        init(self.db_path)
        self.assertEqual(self.version(), SCHEMA_VERSION)
        old = load_request(self.db_path, "old")
        self.assertEqual((old["outcome"], old["failed_after_ms"]), ("provider_error", 5425.6))
        self.assertIsNone(old["provider_request_id"])  # never recorded, not invented
        new_id = save_request(self.db_path, {**FAILED, "provider_request_id": "req_abc"}, [], "prod")
        self.assertEqual(load_request(self.db_path, new_id)["provider_request_id"], "req_abc")
        init(self.db_path)  # re-upgrading is a no-op
        self.assertEqual(len(read_rows(self.db_path, "requests")), 2)

    def test_version_4_rows_are_kept_with_unknown_workload_and_origin(self):
        # Step 012a's requests table (version 4) with one real attempt and its observation.
        with closing(sqlite3.connect(self.db_path)) as conn, conn:
            conn.executescript(STEP_011_REQUESTS.replace(
                "failed_after_ms REAL CHECK (failed_after_ms >= 0),",
                "failed_after_ms REAL CHECK (failed_after_ms >= 0), provider_request_id TEXT,"))
            conn.execute(
                "INSERT INTO requests VALUES ('real1', '2026-10-30T07:16:38.431854Z', 'prod',"
                " 'openai', 'gpt-6-luna', 'success', 17, 64, 14, 0.1, 0.5, 1.7e-06, 7e-06,"
                " 8.7e-06, NULL, 'req_abc')"
            )
            conn.execute(OLD_OBSERVATIONS_V0.replace("value_ms REAL NOT NULL)",
                                                     "value REAL NOT NULL, request_id TEXT)"))
            conn.execute(
                "INSERT INTO observations VALUES (1, '2026-10-30T07:16:38.431854Z', 'prod',"
                " 'openai', 'gpt-6-luna', 'total_latency', 3880.7, 'real1')"
            )
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute("PRAGMA user_version = 4")
        init(self.db_path)
        self.assertEqual(self.version(), SCHEMA_VERSION)
        old = load_request(self.db_path, "real1")
        self.assertEqual(
            [old[k] for k in ("recorded_at", "outcome", "input_tokens", "output_tokens",
                              "total_cost", "provider_request_id")],
            ["2026-10-30T07:16:38.431854Z", "success", 17, 14, 8.7e-06, "req_abc"])
        self.assertEqual(old["metrics"], {"total_latency": 3880.7})
        # Never recorded, so unknown: not guessed from provider or environment.
        self.assertEqual([old["workload_id"], old["origin_cloud"], old["origin_region"]],
                         [None, None, None])
        new_id = save_request(self.db_path, REQUEST, RESULTS, "test")
        self.assertEqual(load_request(self.db_path, new_id)["workload_id"], "simulated.default.v1")
        init(self.db_path)  # re-upgrading is a no-op
        self.assertEqual(len(read_rows(self.db_path, "requests")), 2)

    def test_newer_database_is_refused(self):
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
        with self.assertRaisesRegex(RuntimeError, "newer than this code"):
            connect(self.db_path)


if __name__ == "__main__":
    unittest.main()
