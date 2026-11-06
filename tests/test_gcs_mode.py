"""Tests for the explicitly selected GCS results mode (Step 022).

Covers `real_benchmark.run` with LLM_METRICS_RESULTS_BACKEND=gcs, the storage
preflight, the `gcs_smoke` command, and the 403-on-existing handling of
`GcsObjectStore`. The OpenAI adapter talks to a `fakes.FakeOpener` and GCS is
an in-memory `FakeStore` (or the real client over a fake HTTP session), so no
test reaches a provider, GCS or GCP, and nothing can be billed.
"""

import contextlib
import io
import json
import os
import unittest
from unittest import mock
import urllib.error

from llm_metrics import config
from llm_metrics import gcs_smoke
from llm_metrics import object_results as obj
from llm_metrics import openai_provider
from llm_metrics import real_benchmark
from llm_metrics import targets
from llm_metrics import workloads
from tests import fakes
from tests import test_object_results
from tests.test_object_results import FakeSession
from tests.test_object_results import FakeStore

WORKLOAD = workloads.get_workload("interactive-chat-v1")
BUCKET, PREFIX = "llm-metrics-test-results", "attempts"
GCS_ENV = {
    config.RESULTS_BACKEND_VARIABLE: "gcs",
    config.ORIGIN_CLOUD_VARIABLE: "gcp",
    config.ORIGIN_REGION_VARIABLE: "us-central1",
    obj.RESULTS_BUCKET_VARIABLE: BUCKET,
    obj.RESULTS_PREFIX_VARIABLE: PREFIX,
}
KEY_ENV = {"OPENAI_API_KEY": fakes.FAKE_KEY}


def openai_events(output_tokens=3):
    return fakes.sse(
        {"type": "response.output_text.delta", "delta": "Hello"},
        {"type": "response.output_text.delta", "delta": " there"},
        {
            "type": "response.completed",
            "response": {
                "usage": {
                    "input_tokens": 1795,
                    "output_tokens": output_tokens,
                    "input_tokens_details": {"cached_tokens": 0},
                }
            },
        },
    )


class OverwritingStore(FakeStore):
    """A broken store that ignores the create-only precondition."""

    def create(self, bucket, name, data):
        self.create_calls += 1
        self.objects[(bucket, name)] = bytes(data)


class Harness:
    """Runs `real_benchmark.run` with a fake opener and store."""

    def __init__(self, store=None, opener=None):
        self.store = FakeStore() if store is None else store
        self.opener = opener or fakes.FakeOpener(
            response=fakes.FakeResponse(
                openai_events(), headers={"x-request-id": "req_fake_022"}
            )
        )
        self.factory_calls = 0
        self.adapters = 0

    def factory(self):
        self.factory_calls += 1
        return self.store

    def run(self, env, target=targets.OPENAI, workload=WORKLOAD):
        real_adapter = openai_provider.OpenAIProvider

        def adapter(api_key):
            self.adapters += 1
            return real_adapter(api_key, opener=self.opener)

        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.dict(
            real_benchmark.ADAPTERS, {"openai": adapter}
        ), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = real_benchmark.run(
                target, workload, False, store_factory=self.factory
            )
        return code, out.getvalue(), err.getvalue()

    def records(self, environment="prod"):
        part = f"/v1/requests/{environment}/"
        return {
            name: data
            for (_, name), data in self.store.objects.items()
            if part in name
        }

    def probes(self):
        return [n for (_, n) in self.store.objects if "/v1/preflight/" in n]


class GcsRefusalTest(unittest.TestCase):
    """Configuration refusals happen before the key, adapter or any I/O."""

    def assert_refused(self, env, target=targets.OPENAI, needle=None):
        harness = Harness()
        code, out, err = harness.run(env, target=target)
        self.assertEqual(code, 2)
        self.assertIn("No request was made", err)
        self.assertEqual(harness.factory_calls, 0)
        self.assertEqual(harness.adapters, 0)
        self.assertEqual(harness.opener.calls, [])
        self.assertNotIn("About to make", out)
        self.assertNotIn(fakes.FAKE_KEY, out + err)
        if needle:
            self.assertIn(needle, err)
        return err

    @fakes.no_network
    def test_missing_bucket_or_prefix(self):
        for missing in (
            obj.RESULTS_BUCKET_VARIABLE,
            obj.RESULTS_PREFIX_VARIABLE,
        ):
            env = {**GCS_ENV, **KEY_ENV}
            del env[missing]
            with self.subTest(missing=missing):
                self.assert_refused(env)

    @fakes.no_network
    def test_unsafe_target(self):
        for prefix in ("snapshots/020", "/x", "a//b", "UPPER"):
            env = {**GCS_ENV, **KEY_ENV, obj.RESULTS_PREFIX_VARIABLE: prefix}
            with self.subTest(prefix=prefix):
                err = self.assert_refused(env)
                self.assertNotIn(prefix, err)

    @fakes.no_network
    def test_invalid_backend_value(self):
        env = {**GCS_ENV, **KEY_ENV, config.RESULTS_BACKEND_VARIABLE: "gs"}
        self.assert_refused(env, needle=config.RESULTS_BACKEND_VARIABLE)

    @fakes.no_network
    def test_gcs_requires_gcp_origin(self):
        for cloud in ("local", "aws"):
            env = {**GCS_ENV, **KEY_ENV, config.ORIGIN_CLOUD_VARIABLE: cloud}
            with self.subTest(cloud=cloud):
                self.assert_refused(env, needle="gcp")

    @fakes.no_network
    def test_gcs_is_openai_only(self):
        env = {**GCS_ENV, "ANTHROPIC_API_KEY": "x"}
        self.assert_refused(
            env, target=targets.get_target("anthropic"), needle="OpenAI"
        )

    @fakes.no_network
    def test_missing_key_refuses_before_storage(self):
        self.assert_refused(dict(GCS_ENV), needle="OPENAI_API_KEY")

    @fakes.no_network
    def test_sql_guard_is_unchanged_for_cloud_origin(self):
        base = {
            config.ORIGIN_CLOUD_VARIABLE: "gcp",
            config.ORIGIN_REGION_VARIABLE: "us-central1",
            **KEY_ENV,
        }
        for env in (
            base,  # backend unset = sql
            {**base, config.RESULTS_BACKEND_VARIABLE: "sql"},
            # GCS target settings do not select GCS mode by themselves.
            {**base, obj.RESULTS_BUCKET_VARIABLE: BUCKET,
             obj.RESULTS_PREFIX_VARIABLE: PREFIX},
            # A gs:// URL is never accepted as a database URL.
            {**base, config.DATABASE_URL_VARIABLE: "gs://bucket/x"},
            {**base, config.DATABASE_URL_VARIABLE: "sqlite:///x.db"},
        ):  # fmt: skip
            with self.subTest(env=sorted(env)):
                err = self.assert_refused(env)
                self.assertIn("PostgreSQL", err)


class GcsPreflightTest(unittest.TestCase):

    @fakes.no_network
    def test_preflight_failure_refuses_without_a_paid_request(self):
        for store in (
            FakeStore(create_plan=["denied"]),
            FakeStore(create_plan=["transient_before"]),
            FakeStore(read_plan=["corrupt"]),
            OverwritingStore(),
        ):
            harness = Harness(store=store)
            code, out, err = harness.run({**GCS_ENV, **KEY_ENV})
            with self.subTest(store=type(store).__name__):
                self.assertEqual(code, 2)
                self.assertIn("preflight failed", err)
                self.assertIn("No request was made", err)
                self.assertEqual(harness.adapters, 0)
                self.assertEqual(harness.opener.calls, [])
                self.assertEqual(harness.records(), {})
                self.assertNotIn("About to make", out)

    @fakes.no_network
    def test_client_construction_failure_refuses(self):
        harness = Harness()

        def broken_factory():
            raise RuntimeError(f"no credentials {fakes.SECRETISH}")

        harness.factory = broken_factory
        code, _, err = harness.run({**GCS_ENV, **KEY_ENV})
        self.assertEqual(code, 2)
        self.assertIn("RuntimeError", err)
        self.assertNotIn(fakes.SECRETISH, err)
        self.assertEqual(harness.opener.calls, [])

    def test_preflight_unit(self):
        target = obj.ResultTarget(BUCKET, PREFIX)
        store = FakeStore()
        name = obj.preflight(
            store, target, probe_id="a" * 32, now="2026-11-06T12:00:00.000000Z"
        )
        self.assertEqual(
            name, f"{PREFIX}/v1/preflight/2026-11-06/{'a' * 32}.json"
        )
        self.assertEqual(store.create_calls, 2)  # second one refused
        self.assertEqual(len(store.objects), 1)
        self.assertEqual(
            json.loads(store.objects[(BUCKET, name)]),
            {
                "kind": "llm-metrics.preflight.v1",
                "probe_id": "a" * 32,
                "created_at": "2026-11-06T12:00:00.000000Z",
            },
        )
        with self.assertRaises(obj.RecordIntegrityError):
            obj.preflight(
                OverwritingStore(), target, probe_id="b" * 32,
                now="2026-11-06T12:00:00.000000Z",
            )  # fmt: skip
        with self.assertRaises(obj.InvalidRecordError):
            obj.preflight(store, target, probe_id="../x", now="now")


class GcsPaidPathTest(unittest.TestCase):

    def run_ok(self, harness=None, env=None):
        harness = harness or Harness()
        code, out, err = harness.run(env or {**GCS_ENV, **KEY_ENV})
        return harness, code, out, err

    @fakes.no_network
    def test_one_request_one_complete_record(self):
        harness, code, out, err = self.run_ok()
        self.assertEqual(code, 0, err)
        self.assertEqual(len(harness.opener.calls), 1)
        self.assertEqual(harness.adapters, 1)
        self.assertEqual(len(harness.probes()), 1)
        records = harness.records()
        self.assertEqual(len(records), 1)
        self.assertEqual(harness.records("test"), {})
        ((name, data),) = records.items()
        rec = obj.decode_record(data, expected_name=name)
        facts = rec["request"]
        self.assertEqual(rec["environment"], "prod")
        self.assertEqual(
            (facts["provider"], facts["model"], facts["request_profile_id"]),
            ("openai", "gpt-6-luna", "openai.gpt-6-luna.v1"),
        )
        self.assertEqual(facts["workload_id"], "interactive-chat-v1")
        self.assertEqual(
            (facts["origin_cloud"], facts["origin_region"]),
            ("gcp", "us-central1"),
        )
        self.assertEqual(facts["cache_policy"], "disabled")
        self.assertEqual(facts["requested_max_output_tokens"], 300)
        self.assertEqual(
            (facts["input_tokens"], facts["cached_input_tokens"]), (1795, 0)
        )
        self.assertEqual(facts["output_tokens"], 3)
        self.assertEqual(facts["provider_request_id"], "req_fake_022")
        self.assertEqual(
            (facts["input_price_per_1m"], facts["output_price_per_1m"]),
            (0.1, 0.5),
        )
        self.assertAlmostEqual(facts["total_cost"], 1795 * 0.1e-6 + 3 * 0.5e-6)
        self.assertIsNone(facts["failed_after_ms"])
        metrics = [o["metric"] for o in rec["observations"]]
        self.assertEqual(metrics[:2], ["total_latency", "ttft"])
        # Identity and timing: the id announced before the request is the
        # record's id and name; the summary names the same object.
        self.assertIn(f"Attempt id: {rec['attempt_id']}", out)
        self.assertLess(out.index("Attempt id:"), out.index("Outcome: success"))
        self.assertTrue(name.endswith(f"{rec['attempt_id']}.json"))
        self.assertIn(rec["recorded_at"][:10], name)
        self.assertIn(f"gs://{BUCKET}/{name}", out)
        self.assertIn("created", out)

    @fakes.no_network
    def test_secrets_prompt_and_payload_never_printed_or_stored(self):
        harness, code, out, err = self.run_ok()
        self.assertEqual(code, 0)
        stored = b"".join(harness.store.objects.values())
        for text in (out, err):
            self.assertNotIn(fakes.FAKE_KEY, text)
            self.assertNotIn(WORKLOAD.prompt[:40], text)
            self.assertNotIn('"request":', text)
        self.assertNotIn(fakes.FAKE_KEY.encode(), stored)
        self.assertNotIn(WORKLOAD.prompt[:40].encode(), stored)
        self.assertNotIn(b"Hello there", stored)

    @fakes.no_network
    def test_provider_failure_is_recorded_with_nulls(self):
        error = urllib.error.HTTPError(
            openai_provider.API_URL, 503, "x", {}, io.BytesIO(b"{}")
        )
        harness = Harness(opener=fakes.FakeOpener(error=error))
        code, _, err = harness.run({**GCS_ENV, **KEY_ENV})
        self.assertEqual(code, 0, err)
        self.assertEqual(len(harness.opener.calls), 1)
        (data,) = harness.records().values()
        rec = obj.decode_record(data)
        facts = rec["request"]
        self.assertEqual(facts["outcome"], "provider_error")
        for key in ("input_tokens", "output_tokens", "total_cost"):
            self.assertIsNone(facts[key])
        self.assertIsNotNone(facts["failed_after_ms"])
        self.assertEqual(rec["observations"], [])

    @fakes.no_network
    def test_rejected_request_records_nothing(self):
        error = urllib.error.HTTPError(
            openai_provider.API_URL, 401, "x", {}, io.BytesIO(b"{}")
        )
        harness = Harness(opener=fakes.FakeOpener(error=error))
        code, _, err = harness.run({**GCS_ENV, **KEY_ENV})
        self.assertEqual(code, 2)
        self.assertIn("Nothing was recorded", err)
        self.assertEqual(len(harness.opener.calls), 1)
        self.assertEqual(harness.records(), {})

    @fakes.no_network
    def test_write_failure_after_response_is_exit_3_without_model_retry(self):
        # Preflight: create ok, overwrite refused; then every record create
        # fails transiently.
        store = FakeStore(create_plan=["ok", "ok"] + ["transient_before"] * 5)
        harness = Harness(store=store)
        with mock.patch.object(obj.time, "sleep"):
            code, out, err = harness.run({**GCS_ENV, **KEY_ENV})
        self.assertEqual(code, real_benchmark.EXIT_NOT_PERSISTED)
        self.assertEqual(code, 3)
        self.assertEqual(len(harness.opener.calls), 1)
        self.assertEqual(harness.records(), {})
        attempt_id = out.split("Attempt id: ")[1].split()[0]
        self.assertIn(attempt_id, err)
        self.assertIn("NOT confirmed durable", err)
        self.assertIn("StoreUnavailableError", err)
        self.assertIn("will not be retried", err)
        self.assertNotIn("1795", err)
        self.assertNotIn("req_fake_022", err)
        self.assertNotIn("Saved attempt", out)

    @fakes.no_network
    def test_lost_ack_on_record_is_reconciled(self):
        store = FakeStore(create_plan=["ok", "ok", "transient_after"])
        harness = Harness(store=store)
        with mock.patch.object(obj.time, "sleep"):
            code, out, _ = harness.run({**GCS_ENV, **KEY_ENV})
        self.assertEqual(code, 0)
        self.assertEqual(len(harness.opener.calls), 1)
        self.assertEqual(len(harness.records()), 1)
        self.assertIn("identical object already present", out)

    @fakes.no_network
    def test_conflicting_existing_object_is_exit_3(self):
        # Another writer occupies the record's name with different bytes
        # between measurement and write.
        harness = Harness()
        original_write = obj.write_record

        def racing_write(store, target, record, **kwargs):
            store.objects[(target.bucket, obj.object_name(target, record))] = (
                b"{}"
            )
            return original_write(store, target, record, **kwargs)

        with mock.patch.object(obj, "write_record", racing_write):
            code, out, err = harness.run({**GCS_ENV, **KEY_ENV})
        self.assertEqual(code, 3)
        self.assertIn("RecordConflictError", err)
        self.assertIn(out.split("Attempt id: ")[1].split()[0], err)
        self.assertEqual(len(harness.opener.calls), 1)
        (data,) = harness.records().values()
        self.assertEqual(data, b"{}")  # the existing object is untouched


class GcsSmokeTest(unittest.TestCase):

    def run_smoke(self, env, store=None):
        store = FakeStore() if store is None else store
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = gcs_smoke.run(env, store_factory=lambda: store)
        return code, out.getvalue(), err.getvalue(), store

    @fakes.no_network
    def test_all_checks_pass_and_nothing_lands_in_prod(self):
        code, out, err, store = self.run_smoke(dict(GCS_ENV))
        self.assertEqual(code, 0, err)
        self.assertEqual(out.count("PASS"), 5)
        names = [n for (_, n) in store.objects]
        self.assertEqual(len(names), 2)
        self.assertTrue(any("/v1/preflight/" in n for n in names))
        (record_name,) = [n for n in names if "/v1/requests/" in n]
        self.assertIn("/v1/requests/test/", record_name)
        self.assertFalse(any("/requests/prod/" in n for n in names))
        rec = obj.decode_record(store.objects[(BUCKET, record_name)])
        self.assertEqual(rec["environment"], "test")
        self.assertEqual(rec["request"]["provider"], "dummy")
        self.assertNotIn('"request":', out)

    @fakes.no_network
    def test_refuses_with_any_provider_key_or_bad_config(self):
        cases = [
            {**GCS_ENV, "OPENAI_API_KEY": "x"},
            {**GCS_ENV, "XAI_API_KEY": "x"},
            {
                k: v
                for k, v in GCS_ENV.items()
                if k != config.RESULTS_BACKEND_VARIABLE
            },
            {**GCS_ENV, config.ORIGIN_CLOUD_VARIABLE: "local"},
            {**GCS_ENV, obj.RESULTS_PREFIX_VARIABLE: ""},
        ]
        for env in cases:
            with self.subTest(env=sorted(env)):
                code, _, err, store = self.run_smoke(env)
                self.assertEqual(code, 2)
                self.assertEqual(store.objects, {})
                self.assertIn("Nothing was written", err)

    @fakes.no_network
    def test_storage_failures_fail_the_smoke(self):
        for store in (
            FakeStore(create_plan=["denied"]),
            OverwritingStore(),
            FakeStore(read_plan=["ok", "ok", "corrupt"]),
        ):
            with self.subTest(store=type(store).__name__):
                code, _, err, _ = self.run_smoke(dict(GCS_ENV), store)
                self.assertEqual(code, 1)
                self.assertIn("FAIL at", err)

    def test_command_line(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(gcs_smoke.main(["--real"]), 2)


class Gcs403Test(unittest.TestCase):
    """A create-only identity may get 403 (not 412) for an existing name."""

    def store(self, session):
        # Reuse the real-client-over-fake-session construction.
        return test_object_results.GcsObjectStoreTest.store(self, session)

    @fakes.no_network
    def test_403_on_existing_object_means_exists(self):
        store = self.store(FakeSession(uploads=[403], downloads=[b"{}"]))
        with self.assertRaises(obj.ObjectExistsError):
            store.create("bkt", "a/x", b"{}")

    @fakes.no_network
    def test_403_without_object_is_permission_denied(self):
        store = self.store(FakeSession(uploads=[403], downloads=[404]))
        with self.assertRaises(obj.PermissionDeniedError) as ctx:
            store.create("bkt", "a/x", b"{}")
        self.assertNotIn("SECRET-BODY", str(ctx.exception))


class BackendConfigTest(unittest.TestCase):

    def test_backend_values(self):
        self.assertEqual(config.get_results_backend({}), "sql")
        self.assertEqual(
            config.get_results_backend({config.RESULTS_BACKEND_VARIABLE: ""}),
            "sql",
        )
        for value in ("sql", "gcs"):
            self.assertEqual(
                config.get_results_backend(
                    {config.RESULTS_BACKEND_VARIABLE: value}
                ),
                value,
            )
        for value in ("GCS", "postgres", "sqlite", "gs://x"):
            with self.subTest(value=value):
                with self.assertRaises(config.ConfigError) as ctx:
                    config.get_results_backend(
                        {config.RESULTS_BACKEND_VARIABLE: value}
                    )
                self.assertNotIn(value, str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
