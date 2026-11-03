"""Real PostgreSQL integration tests for the storage layer.

These tests run only when TEST_POSTGRES_URL is set to a local PostgreSQL URL
(hostname must be localhost or 127.0.0.1). They verify that the v7 schema
creation, round-trip persistence, constraint enforcement, atomicity, seeding
idempotency, and the fail-closed orphan-tables behaviour all work against a
live PostgreSQL server.

Run with:
    TEST_POSTGRES_URL=postgresql://user:pass@localhost/dbname \
        python -m unittest tests.test_postgres_integration -v

The test database must already exist and the user must have full privileges on
it. Each test class drops and recreates the application tables in setUp so
every test starts with a clean schema; no data from other tests or runs survives.

Never set TEST_POSTGRES_URL to a shared or production database.
"""

import datetime
import os
import unittest
from urllib.parse import urlparse

import sqlalchemy.exc
from sqlalchemy import create_engine, inspect as sa_inspect, text

from llm_metrics import storage

_URL_VAR = "TEST_POSTGRES_URL"

# Synthetic test fixtures — identical to test_storage.py constants so the
# same semantics are exercised on PostgreSQL.
_DUMMY = {"provider": "dummy", "model": "dummy-model-v1"}
_NEW_FACTS = {
    "workload_id": "simulated.default.v1",
    "origin_cloud": "local",
    "origin_region": "unknown",
    "cache_policy": "provider_default",
    "request_profile_id": "dummy.dummy-model-v1.v1",
}
REQUEST = {
    **_DUMMY,
    **_NEW_FACTS,
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
    **_DUMMY,
    **_NEW_FACTS,
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
    {**_DUMMY, "metric": "total_latency", "value": 180.0},
    {**_DUMMY, "metric": "ttft", "value": 100.0},
    {**_DUMMY, "metric": "output_chunks_per_s", "value": 50.0},
]

_T0 = datetime.datetime(2026, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc)
_T1 = datetime.datetime(2026, 12, 31, 23, 59, 59, tzinfo=datetime.timezone.utc)


def _pg_url() -> str:
    return os.environ.get(_URL_VAR, "")


def _drop_all(url: str) -> None:
    """Drop application tables so each test starts with an empty schema."""
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS observations CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS requests CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
    engine.dispose()


@unittest.skipUnless(os.environ.get(_URL_VAR), f"{_URL_VAR} not set")
class PostgresIntegrationTest(unittest.TestCase):
    """Integration tests against a live local PostgreSQL database."""

    pg_url: str = ""

    @classmethod
    def setUpClass(cls) -> None:
        url = _pg_url()
        parsed = urlparse(url)
        if parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
            raise unittest.SkipTest(
                f"{_URL_VAR} must point to localhost or 127.0.0.1"
                " — never use a shared or cloud database for these tests."
            )
        cls.pg_url = url

    def setUp(self) -> None:
        _drop_all(self.pg_url)
        storage._engines.pop(self.pg_url, None)

    def tearDown(self) -> None:
        engine = storage._engines.pop(self.pg_url, None)
        if engine is not None:
            engine.dispose()

    # ------------------------------------------------------------------
    # Schema lifecycle
    # ------------------------------------------------------------------

    def test_fresh_database_creates_v7_tables_indexes_fk_and_revision(self):
        engine = storage.connect(self.pg_url)
        with engine.connect() as conn:
            insp = sa_inspect(conn)
            self.assertTrue(insp.has_table("requests"))
            self.assertTrue(insp.has_table("observations"))
            self.assertTrue(insp.has_table("alembic_version"))
            indexes = {i["name"] for i in insp.get_indexes("observations")}
            self.assertIn("observations_unique", indexes)
            self.assertIn("observations_request", indexes)
            fks = insp.get_foreign_keys("observations")
            self.assertTrue(
                any(
                    fk["referred_table"] == "requests"
                    and "request_id" in fk["constrained_columns"]
                    for fk in fks
                ),
                "observations.request_id FK not found",
            )
            rev = conn.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar()
        self.assertEqual(rev, "f1a2b3c4d5e6")

    def test_successful_request_round_trips(self):
        request_id = storage.save_request(self.pg_url, REQUEST, RESULTS, "test")
        loaded = storage.load_request(self.pg_url, request_id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["outcome"], "success")
        self.assertEqual(loaded["input_tokens"], 3)
        self.assertEqual(loaded["output_tokens"], 7)
        self.assertAlmostEqual(loaded["total_cost"], 6.2e-05)
        self.assertIsNone(loaded["failed_after_ms"])
        self.assertEqual(
            set(loaded["metrics"].keys()),
            {"total_latency", "ttft", "output_chunks_per_s"},
        )

    def test_failed_request_stores_null_tokens_and_no_observations(self):
        request_id = storage.save_request(self.pg_url, FAILED, [], "test")
        loaded = storage.load_request(self.pg_url, request_id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["outcome"], "rate_limited")
        self.assertIsNone(loaded["input_tokens"])
        self.assertIsNone(loaded["output_tokens"])
        self.assertIsNone(loaded["input_cost"])
        self.assertIsNone(loaded["total_cost"])
        self.assertAlmostEqual(loaded["failed_after_ms"], 12.5)
        self.assertEqual(loaded["metrics"], {})

    # ------------------------------------------------------------------
    # Constraint enforcement
    # ------------------------------------------------------------------

    def test_check_constraint_violation_raises_integrity_error(self):
        # outcome=success with failed_after_ms NOT NULL violates
        # ck_requests_outcome_consistency
        bad = {**REQUEST, "failed_after_ms": 999.0}
        with self.assertRaises(sqlalchemy.exc.IntegrityError):
            storage.save_request(self.pg_url, bad, RESULTS, "test")

    def test_fk_violation_raises_integrity_error(self):
        request_id = storage.save_request(self.pg_url, REQUEST, RESULTS, "test")
        engine = storage.connect(self.pg_url)
        with self.assertRaises(sqlalchemy.exc.IntegrityError):
            with engine.begin() as conn:
                conn.execute(
                    text("DELETE FROM requests WHERE id = :id"),
                    {"id": request_id},
                )

    def test_atomic_rollback_leaves_no_partial_data(self):
        bad = {**REQUEST, "failed_after_ms": 999.0}
        with self.assertRaises(sqlalchemy.exc.IntegrityError):
            storage.save_request(self.pg_url, bad, RESULTS, "test")
        self.assertEqual(
            storage.load_recent_requests(self.pg_url, "test", 10), []
        )

    # ------------------------------------------------------------------
    # Isolation and filtering
    # ------------------------------------------------------------------

    def test_environment_isolation(self):
        storage.save_request(self.pg_url, REQUEST, RESULTS, "test")
        storage.save_request(self.pg_url, REQUEST, RESULTS, "prod")
        test_rows = storage.load_recent_requests(self.pg_url, "test", 10)
        prod_rows = storage.load_recent_requests(self.pg_url, "prod", 10)
        self.assertEqual(len(test_rows), 1)
        self.assertEqual(len(prod_rows), 1)
        self.assertEqual(test_rows[0]["environment"], "test")
        self.assertEqual(prod_rows[0]["environment"], "prod")

    def test_cache_policy_filtering(self):
        cached_req = {**REQUEST, "cache_policy": "enabled"}
        storage.save_request(self.pg_url, REQUEST, RESULTS, "test")
        storage.save_request(self.pg_url, cached_req, RESULTS, "test")
        disabled_obs = storage.load_observations(
            self.pg_url,
            "test",
            "dummy",
            "dummy-model-v1",
            "ttft",
            start=_T0,
            end=_T1,
            cache_policy="provider_default",
        )
        enabled_obs = storage.load_observations(
            self.pg_url,
            "test",
            "dummy",
            "dummy-model-v1",
            "ttft",
            start=_T0,
            end=_T1,
            cache_policy="enabled",
        )
        self.assertEqual(len(disabled_obs), 1)
        self.assertEqual(len(enabled_obs), 1)

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------

    def test_spend_aggregation(self):
        storage.save_request(self.pg_url, REQUEST, RESULTS, "test")
        storage.save_request(self.pg_url, FAILED, [], "test")
        rows = storage.spend_by_model(self.pg_url, "test", start=_T0, end=_T1)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["attempts"], 2)
        self.assertEqual(row["successful_calls"], 1)
        self.assertEqual(row["failed_attempts"], 1)
        self.assertAlmostEqual(row["total_cost"], 6.2e-05)

    # ------------------------------------------------------------------
    # Seeding idempotency
    # ------------------------------------------------------------------

    def test_observation_seeding_is_idempotent(self):
        obs = [(
            _T0,
            {**_DUMMY, "metric": "ttft", "value": 55.0},
        )]
        first = storage.save_new_observations(self.pg_url, obs, "test")
        self.assertEqual(first, 1)
        second = storage.save_new_observations(self.pg_url, obs, "test")
        self.assertEqual(second, 0)
        rows = storage.load_observations(
            self.pg_url, "test", "dummy", "dummy-model-v1", "ttft",
            start=_T0, end=_T1,
        )
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0][1], 55.0)

    # ------------------------------------------------------------------
    # Durability and ordering
    # ------------------------------------------------------------------

    def test_reconnect_and_data_durability(self):
        request_id = storage.save_request(self.pg_url, REQUEST, RESULTS, "test")
        # Evict and reconnect
        old_engine = storage._engines.pop(self.pg_url)
        old_engine.dispose()
        loaded = storage.load_request(self.pg_url, request_id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["id"], request_id)

    def test_readable_timestamps_and_ordering(self):
        id1 = storage.save_request(self.pg_url, REQUEST, RESULTS, "test")
        id2 = storage.save_request(self.pg_url, REQUEST, RESULTS, "test")
        rows = storage.load_recent_requests(self.pg_url, "test", 10)
        self.assertGreaterEqual(len(rows), 2)
        ids = [r["id"] for r in rows]
        self.assertIn(id1, ids)
        self.assertIn(id2, ids)
        # Text-comparable timestamps: most recent first
        ts = [r["recorded_at"] for r in rows]
        self.assertEqual(ts, sorted(ts, reverse=True))
        # Timestamps end with 'Z'
        for t in ts:
            self.assertTrue(t.endswith("Z"), f"timestamp {t!r} missing Z suffix")

    # ------------------------------------------------------------------
    # Fail-closed orphan tables
    # ------------------------------------------------------------------

    def test_orphan_tables_raises_runtime_error_without_alembic_revision(self):
        # Create a requests table without running Alembic migrations.
        bare_engine = create_engine(self.pg_url)
        with bare_engine.begin() as conn:
            conn.execute(
                text("CREATE TABLE requests (id TEXT PRIMARY KEY, note TEXT)")
            )
        bare_engine.dispose()
        # connect() must refuse to stamp silently and raise instead.
        with self.assertRaises(RuntimeError) as ctx:
            storage.connect(self.pg_url)
        msg = str(ctx.exception)
        self.assertIn("existing tables", msg)
        # The error must not include the URL (credentials could be in it).
        self.assertNotIn("@", msg)
        self.assertNotIn(self.pg_url, msg)


# ------------------------------------------------------------------
# Offline credential-safety unit tests (no live database required)
# ------------------------------------------------------------------

class RedactDbUrlTest(unittest.TestCase):

    def test_strips_user_and_password(self):
        url = "postgresql://user:secret@localhost:5432/mydb"
        self.assertEqual(
            storage._redact_db_url(url), "postgresql://localhost:5432/mydb"
        )

    def test_strips_percent_encoded_password(self):
        url = "postgresql://user:p%40ss%25word@127.0.0.1/db"
        self.assertEqual(
            storage._redact_db_url(url), "postgresql://127.0.0.1/db"
        )

    def test_url_without_credentials_unchanged(self):
        url = "postgresql://localhost/db"
        self.assertEqual(storage._redact_db_url(url), url)

    def test_sqlite_url_unchanged(self):
        url = "sqlite:////home/user/data/db.sqlite"
        self.assertEqual(storage._redact_db_url(url), url)
