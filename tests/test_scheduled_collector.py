"""Tests for the scheduled collector and its audit (Step 023). Offline only.

The OpenAI adapter reads from a counting fake opener and GCS is an in-memory
store whose create is atomic under threads and which records a server-side
creation time from an injectable clock. Nothing here reaches OpenAI or GCP.
"""

import contextlib
import datetime
import io
import json
import pathlib
import tempfile
import threading
import unittest
from unittest import mock
import urllib.error

from llm_metrics import collector_audit
from llm_metrics import object_results as obj
from llm_metrics import openai_provider
from llm_metrics import scheduled_collector as sc
from tests import fakes
from tests.test_object_results import FakeStore

UTC = datetime.timezone.utc
START = datetime.datetime(2026, 11, 7, 18, 0, tzinfo=UTC)  # crosses midnight
EXPIRES = START + datetime.timedelta(hours=24)
BUCKET, PREFIX = "llm-metrics-test-results", "attempts"
TARGET = obj.ResultTarget(BUCKET, PREFIX)
ORIGIN = ("gcp", "us-central1")
BASE_ENV = {
    sc.MODE_VARIABLE: "prod",
    sc.START_VARIABLE: "2026-11-07T18:00:00Z",
    sc.EXPIRES_VARIABLE: "2026-11-08T18:00:00Z",
    "LLM_METRICS_RESULTS_BACKEND": "gcs",
    "LLM_METRICS_ORIGIN_CLOUD": "gcp",
    "LLM_METRICS_ORIGIN_REGION": "us-central1",
    obj.RESULTS_BUCKET_VARIABLE: BUCKET,
    obj.RESULTS_PREFIX_VARIABLE: PREFIX,
    "OPENAI_API_KEY": fakes.FAKE_KEY,
}
DRY_ENV = {
    **{k: v for k, v in BASE_ENV.items() if k != "OPENAI_API_KEY"},
    sc.MODE_VARIABLE: "dryrun",
}


def at(minutes_after_start):
    return START + datetime.timedelta(minutes=minutes_after_start)


class ServerStore(FakeStore):
    """FakeStore with atomic create, server creation times and listing."""

    def __init__(self, server_clock=None, **kwargs):
        super().__init__(**kwargs)
        self.lock = threading.Lock()
        self.server_clock = server_clock
        self.times = {}

    def create(self, bucket, name, data):
        with self.lock:
            super().create(bucket, name, data)
            self.times[(bucket, name)] = (
                self.server_clock() if self.server_clock else None
            )

    def created_time(self, bucket, name):
        if (bucket, name) not in self.objects:
            return None
        return self.times.get((bucket, name)) or self.server_time

    server_time = None

    def list_names(self, bucket, prefix):
        return sorted(
            n for (b, n) in self.objects if b == bucket and n.startswith(prefix)
        )


class Opener:
    """Returns a fresh successful (or failing) OpenAI stream per call."""

    def __init__(self, error=None):
        self.calls = 0
        self.error = error
        self.lock = threading.Lock()

    def __call__(self, request, timeout):
        with self.lock:
            self.calls += 1
        if self.error is not None:
            raise self.error
        return fakes.FakeResponse(
            fakes.sse(
                {"type": "response.output_text.delta", "delta": "Hello"},
                {"type": "response.output_text.delta", "delta": " there"},
                {
                    "type": "response.completed",
                    "response": {
                        "usage": {
                            "input_tokens": 1795,
                            "output_tokens": 3,
                            "input_tokens_details": {"cached_tokens": 0},
                        }
                    },
                },
            ),
            headers={"x-request-id": "req_sched"},
        )


class Collector:
    """Runs `sc.run` against shared fakes and captures JSON events."""

    def __init__(self, store=None, opener=None):
        self.store = store
        self.opener = opener or Opener()
        self.factory_calls = 0
        self.adapter_calls = 0

    def factory(self):
        self.factory_calls += 1
        return self.store

    def adapters(self):
        def openai(key):
            self.adapter_calls += 1
            return openai_provider.OpenAIProvider(key, opener=self.opener)

        return {"openai": openai}

    def run(self, when, env=None, clock=None):
        if self.store is None:
            self.store = ServerStore(server_clock=lambda: when)
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch.object(
            obj.time, "sleep"
        ):
            code = sc.run(
                dict(BASE_ENV if env is None else env),
                now=clock or (lambda: when),
                store_factory=self.factory,
                adapters=self.adapters(),
            )
        events = [
            json.loads(line)
            for line in out.getvalue().splitlines()
            if line.startswith("{")
        ]
        return code, events, out.getvalue()


def names(events):
    return [e["event"] for e in events]


class PolicyTest(unittest.TestCase):

    def test_exactly_96_slots_across_midnight(self):
        policy = sc.Policy(START, EXPIRES)
        slots = policy.slots()
        self.assertEqual(len(slots), 96)
        self.assertEqual(slots[0], START)
        self.assertEqual(slots[-1], EXPIRES - sc.SLOT)
        self.assertEqual(len({s.date() for s in slots}), 2)
        self.assertTrue(all(s.minute in (0, 15, 30, 45) for s in slots))
        self.assertFalse(policy.allows(EXPIRES))
        self.assertFalse(policy.allows(START - sc.SLOT))

    def test_invalid_policies_are_refused(self):
        bad = [
            (START + datetime.timedelta(minutes=5), EXPIRES),
            (START, EXPIRES + sc.SLOT),
            (START, EXPIRES - sc.SLOT),
            (START, START),
            (START.replace(tzinfo=None), EXPIRES.replace(tzinfo=None)),
        ]
        for start, expires in bad:
            with self.subTest(start=start, expires=expires):
                with self.assertRaises(sc.CollectorConfigError):
                    sc.Policy(start, expires)
        for env in (
            {},
            {sc.START_VARIABLE: "2026-11-07T18:00:00Z"},
            {sc.START_VARIABLE: "2026-11-07 18:00", sc.EXPIRES_VARIABLE: "x"},
        ):
            with self.subTest(env=env):
                with self.assertRaises(sc.CollectorConfigError):
                    sc.policy_from_environ(env)

    def test_slot_start(self):
        for minute, expected in ((0, 0), (14, 0), (15, 15), (44, 30), (59, 45)):
            moment = START.replace(minute=minute, second=59, microsecond=9)
            self.assertEqual(sc.slot_start(moment).minute, expected)


class RefusalTest(unittest.TestCase):

    def assert_no_spend(self, collector, code, events, expected_code, event):
        self.assertEqual(code, expected_code)
        self.assertEqual(names(events)[-1], event)
        self.assertEqual(collector.opener.calls, 0)
        self.assertEqual(collector.adapter_calls, 0)

    @fakes.no_network
    def test_configuration_refusals_touch_nothing(self):
        cases = {
            "missing mode": {sc.MODE_VARIABLE: ""},
            "bad mode": {sc.MODE_VARIABLE: "live"},
            "sql backend": {"LLM_METRICS_RESULTS_BACKEND": "sql"},
            "local origin": {"LLM_METRICS_ORIGIN_CLOUD": "local"},
            "no bucket": {obj.RESULTS_BUCKET_VARIABLE: ""},
            "reserved prefix": {obj.RESULTS_PREFIX_VARIABLE: "snapshots"},
            "no policy": {sc.START_VARIABLE: ""},
            "48h policy": {sc.EXPIRES_VARIABLE: "2026-11-09T18:00:00Z"},
            "no key": {"OPENAI_API_KEY": ""},
        }
        for label, change in cases.items():
            collector = Collector()
            code, events, _ = collector.run(at(1), env={**BASE_ENV, **change})
            with self.subTest(label):
                self.assert_no_spend(
                    collector, code, events, 2, "config_refused"
                )
                self.assertEqual(collector.factory_calls, 0)
                self.assertEqual(events[-1]["severity"], "ERROR")

    @fakes.no_network
    def test_outside_window_is_a_quiet_no_op(self):
        for when, event in (
            (at(-1), "policy_not_started"),
            (EXPIRES, "policy_expired"),
            (EXPIRES + datetime.timedelta(days=3), "policy_expired"),
        ):
            collector = Collector()
            code, events, _ = collector.run(when)
            with self.subTest(event=event, when=when):
                self.assert_no_spend(collector, code, events, 0, event)
                self.assertEqual(collector.factory_calls, 0)

    @fakes.no_network
    def test_late_start_is_refused(self):
        collector = Collector()
        code, events, _ = collector.run(at(8))
        self.assert_no_spend(collector, code, events, 4, "late_start")
        self.assertEqual(collector.factory_calls, 0)

    @fakes.no_network
    def test_claim_failures_are_refusals(self):
        for store in (
            ServerStore(create_plan=["denied"]),  # preflight denied
            ServerStore(create_plan=["ok", "ok", "transient_before"]),
            ServerStore(create_plan=["ok", "ok", "transient_after"]),
            ServerStore(read_plan=["ok", "ok", "corrupt"]),
        ):
            collector = Collector(store=store)
            code, events, _ = collector.run(at(1))
            with self.subTest(plan=store.create_plan or store.read_plan):
                self.assert_no_spend(collector, code, events, 4, "claim_failed")

    @fakes.no_network
    def test_clock_skew_refuses_and_consumes_the_slot(self):
        store = ServerStore(
            server_clock=lambda: at(1) + datetime.timedelta(minutes=5)
        )
        collector = Collector(store=store)
        code, events, _ = collector.run(at(1))
        self.assert_no_spend(collector, code, events, 4, "clock_skew")
        code, events, _ = collector.run(at(2))
        self.assert_no_spend(collector, code, events, 0, "duplicate_skip")

    @fakes.no_network
    def test_expiry_is_rechecked_immediately_before_the_call(self):
        # Last slot; the clock passes the expiry between claim and request.
        times = iter([at(24 * 60 - 15 + 1)] * 3 + [EXPIRES] * 10)
        store = ServerStore(server_clock=lambda: at(24 * 60 - 14))
        collector = Collector(store=store)
        code, events, _ = collector.run(None, clock=lambda: next(times))
        self.assert_no_spend(collector, code, events, 4, "expired_before_call")


class PaidPathTest(unittest.TestCase):

    @fakes.no_network
    def test_one_call_one_claim_one_record_same_attempt_id(self):
        collector = Collector()
        code, events, out = collector.run(at(2))
        self.assertEqual(code, 0)
        self.assertEqual(collector.opener.calls, 1)
        self.assertEqual(
            names(events),
            ["slot_claimed", "attempt_initiated", "recorded_success"],
        )
        claim = sc.claim_name(TARGET, "prod", ORIGIN, START)
        claim_data = json.loads(collector.store.objects[(BUCKET, claim)])
        self.assertEqual(claim_data["slot"], "2026-11-07T18:00:00Z")
        self.assertEqual(claim_data["profile_id"], "openai.gpt-6-luna.v1")
        self.assertEqual(claim_data["workload_id"], "interactive-chat-v1")
        self.assertEqual(claim_data["policy"]["max_slots"], 96)
        record_name = events[-1]["record"]
        record = obj.read_record(collector.store, TARGET, record_name)
        self.assertEqual(record["attempt_id"], claim_data["attempt_id"])
        self.assertEqual(events[-1]["attempt_id"], claim_data["attempt_id"])
        self.assertEqual(record["environment"], "prod")
        self.assertIn("/v1/requests/prod/", record_name)
        self.assertEqual(record["request"]["provider_request_id"], "req_sched")
        self.assertEqual(events[-1]["slot"], "2026-11-07T18:00:00Z")
        # Sanitized output: no key, prompt, response or record payload.
        self.assertNotIn(fakes.FAKE_KEY, out)
        self.assertNotIn("Hello there", out)
        self.assertNotIn('"observations"', out)

    @fakes.no_network
    def test_duplicate_deliveries_never_call_again(self):
        collector = Collector()
        self.assertEqual(collector.run(at(1))[0], 0)
        for minute in (2, 5, 7):
            code, events, _ = collector.run(at(minute))
            self.assertEqual((code, names(events)), (0, ["duplicate_skip"]))
        self.assertEqual(collector.opener.calls, 1)

    @fakes.no_network
    def test_concurrent_invocations_make_one_call(self):
        store = ServerStore(server_clock=lambda: at(3))
        collector = Collector(store=store)
        barrier = threading.Barrier(8)
        codes = []

        def invoke():
            barrier.wait()
            codes.append(
                sc.run(
                    dict(BASE_ENV),
                    now=lambda: at(3),
                    store_factory=lambda: store,
                    adapters=collector.adapters(),
                )
            )

        with contextlib.redirect_stdout(io.StringIO()):
            threads = [threading.Thread(target=invoke) for _ in range(8)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        self.assertEqual(codes, [0] * 8)
        self.assertEqual(collector.opener.calls, 1)
        claims = [n for (_, n) in store.objects if "/v1/claims/" in n]
        records = [n for (_, n) in store.objects if "/v1/requests/" in n]
        self.assertEqual((len(claims), len(records)), (1, 1))

    @fakes.no_network
    def test_at_most_96_paid_calls_over_the_whole_window(self):
        # A delivery every minute from 30 minutes before activation to 30
        # minutes after expiry, against one shared store.
        collector = Collector(store=ServerStore())
        outcomes = {}
        minute = -30
        while minute < 24 * 60 + 30:
            when = at(minute)
            collector.store.server_clock = lambda when=when: when
            _, events, _ = collector.run(when)
            outcomes[names(events)[-1]] = outcomes.get(names(events)[-1], 0) + 1
            minute += 1
        self.assertEqual(collector.opener.calls, 96)
        self.assertEqual(outcomes["recorded_success"], 96)
        self.assertEqual(outcomes["duplicate_skip"], 96 * 7)
        self.assertEqual(outcomes["late_start"], 96 * 7)
        self.assertEqual(outcomes["policy_not_started"], 30)
        self.assertEqual(outcomes["policy_expired"], 30)

    @fakes.no_network
    def test_provider_failure_is_recorded_with_nulls(self):
        error = urllib.error.HTTPError(
            openai_provider.API_URL, 503, "x", {}, io.BytesIO(b"{}")
        )
        collector = Collector(opener=Opener(error=error))
        code, events, _ = collector.run(at(1))
        self.assertEqual(code, 0)
        self.assertEqual(names(events)[-1], "recorded_failure")
        self.assertEqual(events[-1]["severity"], "WARNING")
        record = obj.read_record(collector.store, TARGET, events[-1]["record"])
        self.assertEqual(record["request"]["outcome"], "provider_error")
        self.assertIsNone(record["request"]["total_cost"])
        self.assertEqual(record["observations"], [])

    @fakes.no_network
    def test_rejected_request_is_an_alert_and_consumes_the_slot(self):
        error = urllib.error.HTTPError(
            openai_provider.API_URL, 401, "x", {}, io.BytesIO(b"{}")
        )
        collector = Collector(opener=Opener(error=error))
        code, events, _ = collector.run(at(1))
        self.assertEqual((code, names(events)[-1]), (2, "provider_rejected"))
        self.assertEqual(collector.run(at(2))[1][-1]["event"], "duplicate_skip")
        self.assertEqual(collector.opener.calls, 1)

    @fakes.no_network
    def test_write_failure_is_exit_3_and_never_retried(self):
        store = ServerStore(
            create_plan=["ok", "ok", "ok"] + ["transient_before"] * 3
        )
        store.server_clock = lambda: at(1)
        collector = Collector(store=store)
        code, events, out = collector.run(at(1))
        self.assertEqual((code, names(events)[-1]), (3, "not_persisted"))
        self.assertEqual(events[-1]["severity"], "ERROR")
        self.assertEqual(events[-1]["error"], "StoreUnavailableError")
        self.assertNotIn("1795", out.split("attempt_initiated")[-1])
        code, events, _ = collector.run(at(2))
        self.assertEqual((code, names(events)), (0, ["duplicate_skip"]))
        self.assertEqual(collector.opener.calls, 1)

    @fakes.no_network
    def test_crash_after_the_request_is_not_retried(self):
        collector = Collector()
        with mock.patch.object(
            obj, "write_record", side_effect=SystemExit("killed")
        ):
            with self.assertRaises(SystemExit):
                collector.run(at(1))
        code, events, _ = collector.run(at(3))
        self.assertEqual((code, names(events)), (0, ["duplicate_skip"]))
        self.assertEqual(collector.opener.calls, 1)
        report = collector_audit.audit(
            collector.store, TARGET, sc.Policy(START, EXPIRES),
            mode="prod", origin=ORIGIN, now=at(10),
        )  # fmt: skip
        self.assertEqual(report["states"], {"claim_without_record": 1})


class DryRunTest(unittest.TestCase):

    @fakes.no_network
    def test_dry_run_claims_without_any_provider(self):
        collector = Collector()
        code, events, _ = collector.run(at(1), env=DRY_ENV)
        self.assertEqual(code, 0)
        self.assertEqual(
            names(events),
            ["slot_claimed", "dryrun_duplicate_refused", "recorded_success"],
        )
        self.assertEqual(
            (collector.adapter_calls, collector.opener.calls), (0, 0)
        )
        stored = [n for (_, n) in collector.store.objects]
        self.assertTrue(any("/v1/claims/dryrun/" in n for n in stored))
        self.assertFalse(any("/v1/claims/prod/" in n for n in stored))
        self.assertFalse(any("/v1/requests/prod/" in n for n in stored))
        record = obj.read_record(collector.store, TARGET, events[-1]["record"])
        self.assertEqual(record["environment"], "test")
        self.assertEqual(record["request"]["provider"], "dummy")

    @fakes.no_network
    def test_dry_run_refuses_with_a_key_and_after_expiry(self):
        collector = Collector()
        code, events, _ = collector.run(
            at(1), env={**DRY_ENV, "OPENAI_API_KEY": "x"}
        )
        self.assertEqual((code, names(events)[-1]), (2, "config_refused"))
        code, events, _ = collector.run(EXPIRES + sc.SLOT, env=DRY_ENV)
        self.assertEqual((code, names(events)[-1]), (0, "policy_expired"))
        self.assertEqual(collector.factory_calls, 0)


class AuditTest(unittest.TestCase):

    def window(self):
        collector = Collector(store=ServerStore())
        for minute in (1, 16, 46):  # slot 30 is never delivered
            collector.store.server_clock = lambda m=minute: at(m)
            collector.run(at(minute))
        # Slot 60: claimed, then the write fails (exit 3).
        collector.store.create_plan = ["ok", "ok", "ok"] + [
            "transient_before"
        ] * 3
        collector.store.server_clock = lambda: at(61)
        self.assertEqual(collector.run(at(61))[0], 3)
        return collector.store

    def test_states_missing_and_claim_without_record(self):
        store = self.window()
        report = collector_audit.audit(
            store, TARGET, sc.Policy(START, EXPIRES),
            mode="prod", origin=ORIGIN, now=at(70),
        )  # fmt: skip
        self.assertEqual(report["expected_slots_so_far"], 5)
        self.assertEqual(report["claimed"], 4)
        self.assertEqual(
            report["states"],
            {"recorded_success": 3, "missing": 1, "claim_without_record": 1},
        )
        problems = {p["slot"]: p["state"] for p in report["problems"]}
        self.assertEqual(
            problems,
            {
                "2026-11-07T18:30:00Z": "missing",
                "2026-11-07T19:00:00Z": "claim_without_record",
            },
        )
        self.assertEqual(report["records_without_claim"], [])

    def test_local_mirror_cli(self):
        store = self.window()
        with tempfile.TemporaryDirectory() as tmp:
            for (_, name), data in store.objects.items():
                path = pathlib.Path(tmp) / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = collector_audit.main([
                    "--start", "2026-11-07T18:00:00Z",
                    "--expires", "2026-11-08T18:00:00Z",
                    "--now", "2026-11-07T19:10:00Z",
                    "--local", tmp,
                ])  # fmt: skip
        self.assertEqual(code, 1)
        report = json.loads(out.getvalue())
        self.assertEqual(report["states"]["missing"], 1)
        self.assertNotIn("1795", out.getvalue())

    def test_bad_arguments(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(collector_audit.main(["--start", "x"]), 2)
            self.assertEqual(sc.main(["--slot", "2026-11-07T18:00:00Z"]), 2)


if __name__ == "__main__":
    unittest.main()
