"""Tests for llm_metrics.object_results (immutable per-attempt JSON records).

Everything is offline. Writer logic runs against `FakeStore`, an in-memory
`ObjectStore` that enforces the create-only precondition and can be scripted
to fail before or after "committing" an object. `GcsObjectStore` is tested with
the real google-cloud-storage client over a fake HTTP session, so the wire
request (precondition, checksum) and error mapping are exercised without GCS.
Passing these tests is not a live cloud durability test.
"""

import copy
import hashlib
import io
import json
import math
import pathlib
import subprocess
import sys
import tempfile
import unittest

from llm_metrics import benchmark
from llm_metrics import latency
from llm_metrics import object_results as obj
from llm_metrics import openai_provider
from llm_metrics import providers
from llm_metrics import storage
from llm_metrics import workloads
from tests import fakes

ATTEMPT_ID = "0123456789abcdef0123456789abcdef"
RECORDED_AT = "2026-11-06T12:00:00.000001Z"
TARGET = obj.ResultTarget("llm-metrics-test-results", "attempts")
SECRET = fakes.SECRETISH


def success_request(**overrides):
    """Synthetic OpenAI-shaped facts of a successful attempt."""
    request = {
        "provider": "openai",
        "model": "gpt-6-luna",
        "outcome": "success",
        "input_tokens": 1000,
        "requested_max_output_tokens": 300,
        "output_tokens": 200,
        "input_price_per_1m": 0.1,
        "output_price_per_1m": 0.5,
        "input_cost": 0.0001,
        "output_cost": 0.0001,
        "total_cost": 0.0002,
        "failed_after_ms": None,
        "provider_request_id": "req_synthetic_0001",
        "workload_id": "interactive-chat-v1",
        "origin_cloud": "gcp",
        "origin_region": "us-central1",
        "cache_policy": "disabled",
        "cached_input_tokens": 0,
        "request_profile_id": "openai.gpt-6-luna.v1",
        "cached_input_price_per_1m": 0.01,
    }
    request.update(overrides)
    return request


def failure_request(**overrides):
    request = success_request(
        outcome="timeout",
        input_tokens=None,
        output_tokens=None,
        input_cost=None,
        output_cost=None,
        total_cost=None,
        cached_input_tokens=None,
        failed_after_ms=30000.5,
        provider_request_id=None,
        diagnostics={"error_code": SECRET, "body": SECRET},
    )
    request.update(overrides)
    return request


def results(provider="openai", model="gpt-6-luna", **values):
    values = values or {
        "ttft": 400.25,
        "total_latency": 2500.5,
        "output_tokens_per_s": 95.0,
        "output_chunks_per_s": 90.5,
    }
    return [
        {"provider": provider, "model": model, "metric": m, "value": v}
        for m, v in values.items()
    ]


def record(request=None, observations=None, **kwargs):
    return obj.build_record(
        success_request() if request is None else request,
        results() if observations is None else observations,
        kwargs.pop("environment", "prod"),
        attempt_id=kwargs.pop("attempt_id", ATTEMPT_ID),
        recorded_at=kwargs.pop("recorded_at", RECORDED_AT),
    )


class FakeStore:
    """In-memory ObjectStore with a create-only precondition and fault plans.

    create plan actions: "ok", "transient_before" (fails, nothing stored),
    "transient_after" (stores, then the acknowledgement is lost), "denied".
    read plan actions: "ok", "transient", "corrupt", "missing".
    """

    def __init__(self, create_plan=(), read_plan=()):
        self.objects = {}
        self.create_plan = list(create_plan)
        self.read_plan = list(read_plan)
        self.create_calls = 0
        self.read_calls = 0

    def create(self, bucket, name, data):
        self.create_calls += 1
        action = self.create_plan.pop(0) if self.create_plan else "ok"
        if action == "transient_before":
            raise obj.TransientStoreError("Transient storage error (HTTP 503).")
        if action == "denied":
            raise obj.ResultStoreError(
                "Storage request failed: Forbidden (HTTP 403)."
            )
        if (bucket, name) in self.objects:
            raise obj.ObjectExistsError("Object already exists (HTTP 412).")
        self.objects[(bucket, name)] = bytes(data)
        if action == "transient_after":
            raise obj.TransientStoreError("Transient storage error (HTTP 503).")

    def read(self, bucket, name):
        self.read_calls += 1
        action = self.read_plan.pop(0) if self.read_plan else "ok"
        if action == "transient":
            raise obj.TransientStoreError("Transient storage error (HTTP 503).")
        if action == "missing":
            return None
        data = self.objects.get((bucket, name))
        if action == "corrupt" and data is not None:
            return data[:-1] + b" "
        return data


class RecordShapeTest(unittest.TestCase):

    def test_success_record_keeps_every_fact_and_observation(self):
        rec = record()
        self.assertEqual(rec["schema_version"], "llm-metrics.attempt.v1")
        self.assertEqual(rec["attempt_id"], ATTEMPT_ID)
        self.assertEqual(rec["recorded_at"], RECORDED_AT)
        self.assertEqual(rec["environment"], "prod")
        expected = success_request()
        self.assertEqual(rec["request"], expected)
        self.assertEqual(
            rec["observations"],
            [
                {"metric": "total_latency", "value": 2500.5},
                {"metric": "ttft", "value": 400.25},
                {"metric": "output_tokens_per_s", "value": 95.0},
                {"metric": "output_chunks_per_s", "value": 90.5},
            ],
        )

    def test_json_round_trip_is_exact(self):
        rec = record()
        data = obj.encode_record(rec)
        self.assertEqual(obj.decode_record(data), rec)
        self.assertEqual(obj.encode_record(obj.decode_record(data)), data)

    def test_failure_keeps_nulls_and_drops_diagnostics(self):
        rec = record(failure_request(), [])
        facts = rec["request"]
        for key in (
            "input_tokens",
            "output_tokens",
            "input_cost",
            "output_cost",
            "total_cost",
            "cached_input_tokens",
            "provider_request_id",
        ):
            self.assertIsNone(facts[key], key)
        self.assertEqual(facts["failed_after_ms"], 30000.5)
        self.assertEqual(rec["observations"], [])
        data = obj.encode_record(rec)
        self.assertIn(b'"input_tokens":null', data)
        self.assertNotIn(SECRET.encode(), data)
        self.assertNotIn(b"diagnostics", data)

    def test_sensitive_extra_keys_never_enter_a_record(self):
        request = success_request(
            prompt="PROMPT-TEXT",
            response="MODEL-OUTPUT",
            api_key=fakes.FAKE_KEY,
            database_url="postgresql://u:pw@h/db",
            headers={"Authorization": "Bearer x"},
        )
        data = obj.encode_record(record(request))
        for needle in (
            b"PROMPT-TEXT",
            b"MODEL-OUTPUT",
            fakes.FAKE_KEY.encode(),
            b"postgresql://",
            b"Bearer",
            b"prompt",
            b"response",
            b"headers",
        ):
            self.assertNotIn(needle, data)

    def test_omitted_optional_facts_are_null(self):
        request = success_request()
        for key in (
            "provider_request_id",
            "cached_input_tokens",
            "cached_input_price_per_1m",
        ):
            del request[key]
        facts = record(request)["request"]
        self.assertIsNone(facts["provider_request_id"])
        self.assertIsNone(facts["cached_input_tokens"])
        self.assertIsNone(facts["cached_input_price_per_1m"])

    def test_canonical_bytes_are_deterministic(self):
        a = obj.encode_record(record())
        shuffled = dict(reversed(list(success_request().items())))
        b = obj.encode_record(record(shuffled, list(reversed(results()))))
        c = obj.encode_record(record(success_request(input_price_per_1m=0.1)))
        self.assertEqual(a, b)
        self.assertEqual(a, c)
        self.assertNotIn(b" ", a)
        self.assertNotIn(b"\n", a)
        # An integral price given as int encodes as the same float as 1.0.
        self.assertEqual(
            obj.encode_record(record(success_request(output_price_per_1m=1))),
            obj.encode_record(record(success_request(output_price_per_1m=1.0))),
        )

    def test_request_fields_match_storage_columns(self):
        identity = {"id", "recorded_at", "environment"}
        self.assertEqual(
            obj.REQUEST_FIELDS,
            tuple(
                c
                for c in storage._REQUEST_COLUMNS  # pylint: disable=protected-access
                if c not in identity
            ),
        )
        self.assertEqual(obj.ENVIRONMENTS, ("test", "prod"))

    def test_metrics_and_units_are_the_latency_contract(self):
        names = [o["metric"] for o in record()["observations"]]
        self.assertEqual(names, list(latency.METRICS))
        self.assertEqual(latency.METRICS["ttft"][1], "ms")
        self.assertEqual(latency.METRICS["total_latency"][1], "ms")
        self.assertEqual(latency.METRICS["output_tokens_per_s"][1], "tokens/s")


class ValidationTest(unittest.TestCase):

    def assert_invalid(self, rec):
        with self.assertRaises(obj.InvalidRecordError):
            obj.validate_record(rec)

    def test_rejects_other_schema_versions_and_shapes(self):
        for version in ("llm-metrics.attempt.v2", "v1", None, 1):
            rec = record()
            rec["schema_version"] = version
            with self.subTest(version=version):
                self.assert_invalid(rec)
        for bad in ({}, [], None, "x"):
            with self.subTest(bad=bad):
                self.assert_invalid(bad)
        rec = record()
        rec["extra"] = 1
        self.assert_invalid(rec)
        rec = record()
        del rec["observations"]
        self.assert_invalid(rec)
        rec = record()
        rec["request"]["extra"] = 1
        self.assert_invalid(rec)

    def test_rejects_bad_identity_time_and_environment(self):
        cases = {
            "attempt_id": ["0123", ATTEMPT_ID.upper(), "g" * 32, 123],
            "recorded_at": [
                "2026-11-06T12:00:00Z",
                "2026-11-06T12:00:00.000001+00:00",
                "2026-02-30T12:00:00.000000Z",
                "",
            ],
            "environment": ["staging", "", None],
        }
        for key, values in cases.items():
            for value in values:
                rec = record()
                rec[key] = value
                with self.subTest(key=key, value=value):
                    self.assert_invalid(rec)

    def test_rejects_invalid_request_facts(self):
        nan = math.nan
        cases = [
            {"outcome": "ok"},
            {"cache_policy": "unknown"},
            {"cache_policy": "sometimes"},
            {"workload_id": ""},
            {"origin_region": None},
            {"request_profile_id": None},
            {"provider_request_id": ""},
            {"input_tokens": -1},
            {"input_tokens": True},
            {"input_tokens": 1.5},
            {"requested_max_output_tokens": 0},
            {"input_price_per_1m": nan},
            {"input_price_per_1m": -0.1},
            {"input_price_per_1m": None},
            {"total_cost": None},
            {"total_cost": math.inf},
            {"failed_after_ms": 1.0},
            {"cached_input_tokens": 1001},
            {"output_tokens": 301},
        ]
        for change in cases:
            rec = record()
            rec["request"].update(change)
            with self.subTest(change=change):
                self.assert_invalid(rec)

    def test_failure_must_not_carry_success_facts(self):
        for change in (
            {"input_tokens": 0},
            {"total_cost": 0.0},
            {"failed_after_ms": None},
            {"cached_input_tokens": 0},
        ):
            rec = record(failure_request(), [])
            rec["request"].update(change)
            with self.subTest(change=change):
                self.assert_invalid(rec)
        with self.assertRaises(obj.InvalidRecordError):
            record(failure_request(), results())

    def test_rejects_invalid_observations(self):
        cases = [
            [{"metric": "ttft", "value": 1.0}],  # no total_latency
            [
                {"metric": "total_latency", "value": 1.0},
                {"metric": "ttft", "value": 1.0},
                {"metric": "ttft", "value": 2.0},
            ],
            [
                {"metric": "total_latency", "value": 1.0},
                {"metric": "ttft", "value": 1.0},
                {"metric": "cost", "value": 1.0},
            ],
            [
                {"metric": "ttft", "value": 1.0},
                {"metric": "total_latency", "value": 1.0},
            ],  # not in METRICS order
            [
                {"metric": "total_latency", "value": -1.0},
                {"metric": "ttft", "value": 1.0},
            ],
            [
                {"metric": "total_latency", "value": 1.0, "unit": "ms"},
                {"metric": "ttft", "value": 1.0},
            ],
        ]
        for observations in cases:
            rec = record()
            rec["observations"] = observations
            with self.subTest(observations=observations):
                self.assert_invalid(rec)

    def test_builder_rejects_missing_facts_and_foreign_observations(self):
        request = success_request()
        del request["workload_id"]
        with self.assertRaises(obj.InvalidRecordError):
            record(request)
        with self.assertRaises(obj.InvalidRecordError):
            record(observations=results(model="other-model"))

    def test_decode_rejects_non_canonical_or_unsafe_json(self):
        rec = record()
        data = obj.encode_record(rec)
        pretty = json.dumps(rec, indent=2, sort_keys=True).encode()
        duplicate = data[:-1] + b',"environment":"prod"}'
        nan = data.replace(b'"ttft","value":400.25', b'"ttft","value":NaN')
        for bad in (pretty, duplicate, nan, b"", b"[]", b"\xff\xfe", b"{}"):
            with self.subTest(bad=bad[:30]):
                with self.assertRaises(obj.InvalidRecordError):
                    obj.decode_record(bad)

    def test_error_messages_name_fields_not_values(self):
        rec = record(success_request(workload_id=SECRET))
        rec["request"]["outcome"] = SECRET
        with self.assertRaises(obj.InvalidRecordError) as ctx:
            obj.validate_record(rec)
        self.assertNotIn(SECRET, str(ctx.exception))


class TargetAndNameTest(unittest.TestCase):

    def test_valid_target_and_object_name(self):
        rec = record()
        name = obj.object_name(TARGET, rec)
        self.assertEqual(
            name, f"attempts/v1/requests/prod/2026-11-06/{ATTEMPT_ID}.json"
        )
        self.assertNotIn("req_synthetic", name)
        test_name = obj.object_name(TARGET, record(environment="test"))
        self.assertIn("/requests/test/", test_name)
        self.assertEqual(
            obj.ResultTarget("abc", "a/b-c/d_e").prefix, "a/b-c/d_e"
        )

    def test_rejects_missing_or_unsafe_targets(self):
        bad = [
            ("", "attempts"),
            ("ab", "attempts"),
            ("Upper-Bucket", "attempts"),
            ("bucket.with.dots", "attempts"),
            ("goog-results", "attempts"),
            ("my-google-bucket", "attempts"),
            ("bucket-", "attempts"),
            ("results", ""),
            ("results", "/attempts"),
            ("results", "attempts/"),
            ("results", "a//b"),
            ("results", "a/../b"),
            ("results", "."),
            ("results", "Attempts"),
            ("results", "gs://x"),
            ("results", "snapshots"),
            ("results", "snapshots/020"),
            (None, "attempts"),
        ]
        for bucket, prefix in bad:
            with self.subTest(bucket=bucket, prefix=prefix):
                with self.assertRaises(obj.TargetConfigError):
                    obj.ResultTarget(bucket, prefix)

    def test_target_from_environ_requires_explicit_values(self):
        with self.assertRaises(obj.TargetConfigError):
            obj.target_from_environ({})
        with self.assertRaises(obj.TargetConfigError):
            obj.target_from_environ({obj.RESULTS_BUCKET_VARIABLE: "results"})
        target = obj.target_from_environ(
            {
                obj.RESULTS_BUCKET_VARIABLE: "results",
                obj.RESULTS_PREFIX_VARIABLE: "attempts",
            }
        )
        self.assertEqual(target, obj.ResultTarget("results", "attempts"))


class WriterTest(unittest.TestCase):

    def write(self, store, rec=None, **kwargs):
        self.sleeps = []
        return obj.write_record(
            store, TARGET, record() if rec is None else rec,
            sleep=self.sleeps.append, **kwargs,
        )  # fmt: skip

    def only_object(self, store):
        self.assertEqual(len(store.objects), 1)
        return next(iter(store.objects.values()))

    def test_creates_exactly_one_complete_object(self):
        store = FakeStore()
        result = self.write(store)
        data = obj.encode_record(record())
        self.assertTrue(result.created)
        self.assertEqual(result.sha256, hashlib.sha256(data).hexdigest())
        self.assertEqual(list(store.objects), [(TARGET.bucket, result.name)])
        self.assertEqual(self.only_object(store), data)
        self.assertEqual((store.create_calls, store.read_calls), (1, 1))

    def test_identical_replay_is_idempotent(self):
        store = FakeStore()
        first = self.write(store)
        again = self.write(store)
        self.assertFalse(again.created)
        self.assertEqual(first.sha256, again.sha256)
        self.assertEqual(self.only_object(store), obj.encode_record(record()))

    def test_conflicting_payload_is_rejected_not_overwritten(self):
        store = FakeStore()
        self.write(store)
        different = record(success_request(output_tokens=201))
        with self.assertRaises(obj.RecordConflictError):
            self.write(store, different)
        self.assertEqual(self.only_object(store), obj.encode_record(record()))

    def test_concurrent_writers_cannot_overwrite_each_other(self):
        store = FakeStore()
        a = record()
        b = record(success_request(origin_region="europe-west1"))
        self.write(store, a)
        with self.assertRaises(obj.RecordConflictError):
            self.write(store, b)
        self.write(store, a)
        self.assertEqual(self.only_object(store), obj.encode_record(a))
        # Different attempts never share a name.
        self.write(store, record(attempt_id="f" * 32))
        self.assertEqual(len(store.objects), 2)

    def test_transient_failure_before_create_is_retried(self):
        store = FakeStore(create_plan=["transient_before"])
        result = self.write(store)
        self.assertTrue(result.created)
        self.assertEqual(store.create_calls, 2)
        self.assertEqual(self.sleeps, [0.5])

    def test_lost_acknowledgement_reconciles_without_a_second_object(self):
        store = FakeStore(create_plan=["transient_after"])
        result = self.write(store)
        self.assertFalse(result.created)  # confirmed by matching read
        self.assertEqual(store.create_calls, 2)
        self.assertEqual(self.only_object(store), obj.encode_record(record()))

    def test_retries_are_bounded_and_failure_is_not_durable(self):
        store = FakeStore(create_plan=["transient_before"] * 10)
        with self.assertRaises(obj.StoreUnavailableError) as ctx:
            self.write(store)
        self.assertEqual(store.create_calls, obj.DEFAULT_MAX_ATTEMPTS)
        self.assertEqual(self.sleeps, [0.5, 2.0])
        self.assertIn("not confirmed durable", str(ctx.exception))
        self.assertEqual(store.objects, {})
        store = FakeStore(create_plan=["transient_before"] * 10)
        with self.assertRaises(obj.StoreUnavailableError):
            self.write(store, max_attempts=1)
        self.assertEqual((store.create_calls, self.sleeps), (1, []))

    def test_permanent_failure_is_not_retried(self):
        store = FakeStore(create_plan=["denied"])
        with self.assertRaises(obj.ResultStoreError) as ctx:
            self.write(store)
        self.assertNotIsInstance(ctx.exception, obj.StoreUnavailableError)
        self.assertEqual(store.create_calls, 1)

    def test_read_back_mismatch_and_disappearance_fail(self):
        with self.assertRaises(obj.RecordIntegrityError):
            self.write(FakeStore(read_plan=["corrupt"]))
        with self.assertRaises(obj.RecordIntegrityError):
            self.write(FakeStore(read_plan=["missing"]))

    def test_transient_read_back_is_retried_and_reconciled(self):
        store = FakeStore(read_plan=["transient"])
        result = self.write(store)
        self.assertEqual(store.create_calls, 2)
        self.assertEqual(self.only_object(store), obj.encode_record(record()))
        self.assertFalse(result.created)

    def test_invalid_record_writes_nothing(self):
        store = FakeStore()
        bad = record()
        bad["request"]["outcome"] = "maybe"
        with self.assertRaises(obj.InvalidRecordError):
            self.write(store, bad)
        self.assertEqual((store.create_calls, store.objects), (0, {}))
        with self.assertRaises(ValueError):
            self.write(store, max_attempts=0)

    def test_errors_never_contain_record_content(self):
        store = FakeStore(create_plan=["transient_before"] * 3)
        rec = record(success_request(provider_request_id="req_" + "z" * 20))
        with self.assertRaises(obj.StoreUnavailableError) as ctx:
            self.write(store, rec)
        self.assertNotIn("req_zzz", str(ctx.exception))
        self.assertNotIn("1000", str(ctx.exception))


class ReadTest(unittest.TestCase):

    def test_read_back_into_storage_rows_without_loss(self):
        store = FakeStore()
        result = obj.write_record(store, TARGET, record(), sleep=lambda s: None)
        rec = obj.read_record(store, TARGET, result.name)
        request_row, observation_rows = obj.to_storage_rows(rec)
        self.assertEqual(
            request_row,
            {
                "id": ATTEMPT_ID,
                "recorded_at": RECORDED_AT,
                "environment": "prod",
                **success_request(),
            },
        )
        self.assertEqual(
            {r["metric"]: r["value"] for r in observation_rows},
            {
                "total_latency": 2500.5,
                "ttft": 400.25,
                "output_tokens_per_s": 95.0,
                "output_chunks_per_s": 90.5,
            },
        )
        for row in observation_rows:
            self.assertEqual(row["request_id"], ATTEMPT_ID)
            self.assertEqual(row["recorded_at"], RECORDED_AT)
            self.assertEqual(
                (row["provider"], row["model"]), ("openai", "gpt-6-luna")
            )

    def test_read_rejects_missing_misplaced_and_foreign_objects(self):
        store = FakeStore()
        result = obj.write_record(store, TARGET, record(), sleep=lambda s: None)
        with self.assertRaises(obj.InvalidRecordError):
            obj.read_record(store, TARGET, "elsewhere/" + result.name)
        with self.assertRaises(obj.ResultStoreError):
            obj.read_record(
                store, TARGET, result.name.replace(ATTEMPT_ID, "e" * 32)
            )
        moved = result.name.replace("2026-11-06", "2026-11-07")
        store.objects[(TARGET.bucket, moved)] = store.objects[
            (TARGET.bucket, result.name)
        ]
        with self.assertRaises(obj.InvalidRecordError):
            obj.read_record(store, TARGET, moved)


class StorageCompatibilityTest(unittest.TestCase):
    """Records agree with what the existing SQL path stores for an attempt."""

    def stored_row(self, db_path, request_id):
        row = storage.load_request(db_path, request_id)
        self.assertIsNotNone(row)
        metrics = row.pop("metrics")
        # Release the cached engine of this temporary database.
        url = f"sqlite:///{db_path.resolve()}"
        engine = storage._engines.pop(  # pylint: disable=protected-access
            url, None
        )
        if engine is not None:
            engine.dispose()
        return dict(row), metrics

    @fakes.no_network
    def test_openai_attempt_maps_exactly_to_its_sql_row(self):
        events = fakes.sse(
            {"type": "response.output_text.delta", "delta": "Hello"},
            {"type": "response.output_text.delta", "delta": " there"},
            {
                "type": "response.completed",
                "response": {
                    "usage": {
                        "input_tokens": 40,
                        "output_tokens": 3,
                        "input_tokens_details": {"cached_tokens": 8},
                    }
                },
            },
        )
        opener = fakes.FakeOpener(
            response=fakes.FakeResponse(
                events, headers={"x-request-id": "req_fake"}
            )
        )
        provider = openai_provider.OpenAIProvider(fakes.FAKE_KEY, opener=opener)
        with tempfile.TemporaryDirectory() as tmp:
            db_path = pathlib.Path(tmp) / "x.db"
            request, results_, request_id = benchmark.run_attempt(
                provider,
                workloads.SMOKE_SHORT_TEXT_V2,
                "prod",
                db_path,
                origin=("gcp", "us-central1"),
            )
            row, metrics = self.stored_row(db_path, request_id)
        rec = obj.build_record(
            request, results_, "prod",
            attempt_id=request_id, recorded_at=row["recorded_at"],
        )  # fmt: skip
        request_row, observation_rows = obj.to_storage_rows(rec)
        self.assertEqual(request_row, row)
        self.assertEqual(
            {o["metric"]: o["value"] for o in observation_rows}, metrics
        )
        self.assertEqual(request_row["cached_input_tokens"], 8)
        self.assertEqual(request_row["provider_request_id"], "req_fake")
        self.assertNotIn(fakes.FAKE_KEY.encode(), obj.encode_record(rec))

    def test_failed_attempt_maps_exactly_to_its_sql_row(self):
        provider = providers.DummyProvider(
            first_token_delay_s=0, inter_token_delay_s=0, fail_with="timeout"
        )
        with tempfile.TemporaryDirectory() as tmp:
            db_path = pathlib.Path(tmp) / "x.db"
            request, results_, request_id = benchmark.run_attempt(
                provider,
                workloads.get_workload(workloads.DEFAULT_WORKLOAD_ID),
                "test",
                db_path,
                origin=("local", "unknown"),
            )
            row, metrics = self.stored_row(db_path, request_id)
        rec = obj.build_record(
            request, results_, "test",
            attempt_id=request_id, recorded_at=row["recorded_at"],
        )  # fmt: skip
        request_row, observation_rows = obj.to_storage_rows(rec)
        self.assertEqual(request_row, row)
        self.assertEqual((observation_rows, metrics), ([], {}))
        self.assertIsNone(request_row["total_cost"])
        self.assertNotIn(b"simulated failure", obj.encode_record(rec))

    def test_step_020_measurement_round_trips_exactly(self):
        # Values as verified from PostgreSQL in prompts/020-output.md.
        request_row = {
            "id": "13caf417c6ba434fa378cc816f318379",
            "recorded_at": "2026-11-06T14:51:34.612374Z",
            "environment": "prod",
            "provider": "openai",
            "model": "gpt-6-luna",
            "outcome": "success",
            "input_tokens": 1795,
            "requested_max_output_tokens": 300,
            "output_tokens": 300,
            "input_price_per_1m": 0.1,
            "output_price_per_1m": 0.5,
            "input_cost": 0.0001795,
            "output_cost": 0.00015,
            "total_cost": 0.0003295,
            "failed_after_ms": None,
            "provider_request_id": "req_d382c49777f049e384ffdb38bda6c827",
            "workload_id": "interactive-chat-v1",
            "origin_cloud": "gcp",
            "origin_region": "us-central1",
            "cache_policy": "disabled",
            "cached_input_tokens": 0,
            "request_profile_id": "openai.gpt-6-luna.v1",
            "cached_input_price_per_1m": 0.01,
        }
        values = {
            "total_latency": 5343.39077300001,
            "ttft": 2469.919594000203,
            "output_tokens_per_s": 105.32037938071073,
            "output_chunks_per_s": 103.91610765563459,
        }
        observation_rows = [
            {
                "recorded_at": request_row["recorded_at"],
                "environment": "prod",
                "provider": "openai",
                "model": "gpt-6-luna",
                "metric": metric,
                "value": value,
                "request_id": request_row["id"],
            }
            for metric, value in values.items()
        ]
        rec = obj.from_storage_rows(request_row, observation_rows)
        data = obj.encode_record(rec)
        back_request, back_observations = obj.to_storage_rows(
            obj.decode_record(data)
        )
        self.assertEqual(back_request, request_row)
        self.assertEqual(back_observations, observation_rows)
        name = obj.object_name(TARGET, rec)
        self.assertTrue(
            name.endswith(
                "/prod/2026-11-06/13caf417c6ba434fa378cc816f318379.json"
            )
        )
        wrong = copy.deepcopy(observation_rows)
        wrong[0]["request_id"] = "f" * 32
        with self.assertRaises(obj.InvalidRecordError):
            obj.from_storage_rows(request_row, wrong)


class FakeSession:
    """Stands in for the HTTP session under a real google-cloud-storage Client.

    Routes by URL (the client also fetches bucket metadata in a background
    thread; that request gets 403, which the library tolerates). Upload and
    download responses are scripted per call; a scripted upload may "commit"
    the object before responding with an error, as a lost acknowledgement.
    """

    is_mtls = False

    def __init__(self, uploads=(), downloads=()):
        import requests  # pylint: disable=import-outside-toplevel

        self._requests = requests
        self.uploads, self.downloads = list(uploads), list(downloads)
        self.upload_calls, self.download_calls = [], []
        self.committed = None

    def _response(self, status, body=b"", headers=None):
        import urllib3  # pylint: disable=import-outside-toplevel

        headers = headers or {"content-type": "application/json"}
        response = self._requests.Response()
        response.status_code = status
        # A real urllib3 response, so the client's streaming download path
        # (raw.headers, raw.stream) runs unchanged.
        response.raw = urllib3.HTTPResponse(
            body=io.BytesIO(body),
            headers=headers,
            status=status,
            preload_content=False,
        )
        response.headers.update(headers)
        response.request = self._requests.Request("GET", "https://x").prepare()
        return response

    def _error(self, status):
        body = json.dumps(
            {"error": {"code": status, "message": f"SECRET-BODY {SECRET}"}}
        ).encode()
        return self._response(status, body)

    def request(self, method, url, data=None, headers=None, **unused_kwargs):
        if "uploadType=" in url:
            self.upload_calls.append((method, url, data, headers))
            action = self.uploads.pop(0) if self.uploads else 200
            if action == "reset":
                raise self._requests.exceptions.ConnectionError(
                    f"connection reset token=abc {SECRET}"
                )
            if action in (200, "commit+503"):
                self.committed = data
            if action == 200:
                body = json.dumps(
                    {"name": "n", "bucket": "b", "generation": "1"}
                )
                return self._response(200, body.encode())
            return self._error(503 if action == "commit+503" else action)
        if "alt=media" in url:
            self.download_calls.append(url)
            action = self.downloads.pop(0) if self.downloads else 200
            if isinstance(action, bytes):
                return self._response(
                    200, action, {"content-type": "application/json"}
                )
            return self._error(action)
        return self._error(403)  # bucket metadata prefetch


class GcsObjectStoreTest(unittest.TestCase):
    """Real client library, fake HTTP transport; never contacts GCS."""

    def store(self, session):
        # pylint: disable=import-outside-toplevel
        from google.auth.credentials import AnonymousCredentials
        from google.cloud import storage as gcs

        # pylint: enable=import-outside-toplevel

        client = gcs.Client(
            project="llm-metrics-offline-test",
            credentials=AnonymousCredentials(),
            _http=session,
        )
        return obj.GcsObjectStore(client)

    @fakes.no_network
    def test_create_is_create_only_with_content_checksum(self):
        session = FakeSession()
        data = obj.encode_record(record())
        self.store(session).create("results-bucket", "attempts/x.json", data)
        method, url, body, _ = session.upload_calls[0]
        self.assertEqual(method, "POST")
        self.assertIn("/b/results-bucket/o?", url)
        self.assertIn("ifGenerationMatch=0", url)
        self.assertIn(data, body)
        md5 = __import__("base64").b64encode(hashlib.md5(data).digest())
        self.assertIn(b'"md5Hash": "' + md5 + b'"', body)
        self.assertIn(b"application/json", body)

    @fakes.no_network
    def test_errors_are_translated_and_sanitized(self):
        data = b"{}"
        cases = [
            (412, obj.ObjectExistsError),
            (503, obj.TransientStoreError),
            (429, obj.TransientStoreError),
            (500, obj.TransientStoreError),
            ("reset", obj.TransientStoreError),
            (403, obj.ResultStoreError),
            (400, obj.ResultStoreError),
        ]
        for action, expected in cases:
            with self.subTest(action=action):
                with self.assertRaises(expected) as ctx:
                    self.store(FakeSession(uploads=[action])).create(
                        "bkt", "a/x", data
                    )
                if expected is obj.ResultStoreError:
                    self.assertNotIsInstance(
                        ctx.exception, obj.TransientStoreError
                    )
                message = str(ctx.exception)
                self.assertNotIn("SECRET-BODY", message)
                self.assertNotIn("token=abc", message)
                self.assertNotIn(SECRET, message)
                self.assertIsNone(ctx.exception.__cause__)

    @fakes.no_network
    def test_read_returns_bytes_or_none(self):
        store = self.store(FakeSession(downloads=[b'{"a":1}', 404, 503]))
        self.assertEqual(store.read("bkt", "a/x"), b'{"a":1}')
        self.assertIsNone(store.read("bkt", "a/x"))
        with self.assertRaises(obj.TransientStoreError):
            store.read("bkt", "a/x")

    @fakes.no_network
    def test_lost_acknowledgement_end_to_end_through_the_client(self):
        data = obj.encode_record(record())
        session = FakeSession(uploads=["commit+503", 412], downloads=[data])
        result = obj.write_record(
            self.store(session), TARGET, record(), sleep=lambda s: None
        )
        self.assertFalse(result.created)
        self.assertEqual(len(session.upload_calls), 2)
        self.assertIn(data, session.committed)

    @fakes.no_network
    def test_conflict_end_to_end_through_the_client(self):
        other = obj.encode_record(record(success_request(output_tokens=1)))
        session = FakeSession(uploads=[412], downloads=[other])
        with self.assertRaises(obj.RecordConflictError):
            obj.write_record(
                self.store(session), TARGET, record(), sleep=lambda s: None
            )
        self.assertEqual(len(session.upload_calls), 1)


class BoundaryTest(unittest.TestCase):
    """No eager cloud imports; SQL modules stay independent of records."""

    def test_import_does_not_load_cloud_client(self):
        code = (
            "import sys; import llm_metrics.object_results;"
            " print('google.cloud.storage' in sys.modules)"
        )
        out = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            check=True,
            cwd=pathlib.Path(__file__).resolve().parent.parent,
        )
        self.assertEqual(out.stdout.strip(), "False")

    def test_sql_paths_do_not_use_object_results(self):
        # Step 022 wires records into real_benchmark's explicit GCS mode only
        # (tests/test_gcs_mode.py); the measurement and SQL modules stay free
        # of it.
        package = pathlib.Path(obj.__file__).parent
        for module in ("benchmark.py", "storage.py", "real_smoke.py"):
            with self.subTest(module=module):
                self.assertNotIn(
                    "object_results", (package / module).read_text()
                )


if __name__ == "__main__":
    unittest.main()
