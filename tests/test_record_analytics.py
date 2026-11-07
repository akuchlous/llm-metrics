"""Tests for offline analytics over a local GCS mirror (Step 024).

Uses the committed synthetic mirror in `tests/fixtures/gcs_mirror/` (built by
`tests.analytics_fixtures`), copied to a temporary directory whenever a test
damages it. Nothing here reaches GCP, OpenAI or a database.
"""

import contextlib
import datetime
import hashlib
import io
import json
import os
import pathlib
import shutil
import tempfile
import unittest
from unittest import mock

from llm_metrics import object_results as obj
from llm_metrics import record_analytics as ra
from tests import analytics_fixtures as fx
from tests import fakes

UTC = datetime.timezone.utc
DAY_DIR = "attempts/v1/requests/prod/2026-01-05"
POLICY = "2026-01-05T18:00:00Z"


def population(**overrides):
    values = {
        "provider": "openai",
        "model": "gpt-6-luna",
        "request_profile_id": "openai.gpt-6-luna.v1",
        "workload_id": "interactive-chat-v1",
        "origin_cloud": "gcp",
        "origin_region": "us-central1",
        "start": fx.POLICY_START,
        "end": fx.WINDOW_END,
    }
    values.update(overrides)
    return ra.Population(**values)


def cli_args(mirror, output, *extra, end="2026-01-05T20:00:00Z"):
    return [
        "--input", str(mirror), "--output", str(output),
        "--provider", "openai", "--model", "gpt-6-luna",
        "--profile", "openai.gpt-6-luna.v1",
        "--workload", "interactive-chat-v1", "--origin", "gcp/us-central1",
        "--start", "2026-01-05T18:00:00Z", "--end", end, *extra,
    ]  # fmt: skip


def run_cli(args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = ra.main(args)
        except SystemExit as exit_:  # argparse usage errors
            code = exit_.code
    return code, out.getvalue(), err.getvalue()


def record_bytes(number, recorded_at, model="gpt-6-luna", **facts):
    """A valid extra record for one test (not part of the fixture mirror)."""
    return obj.encode_record(
        fx.record(
            number,
            recorded_at,
            fx.request_facts(number, model=model, **facts),
            fx.observations(1000.0, 2000.0, 100.0, model=model),
        )
    )


class MirrorTestCase(unittest.TestCase):
    """Gives each test a private, writable copy of the fixture mirror."""

    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.mirror = self.tmp / "mirror"
        shutil.copytree(fx.FIXTURE_ROOT, self.mirror)
        self.output = self.tmp / "out" / "summary.json"
        self.output.parent.mkdir()

    def build(self, policy_start=fx.POLICY_START, **overrides):
        return json.loads(
            ra.build(
                self.mirror, "attempts", population(**overrides), policy_start
            )
        )

    def assert_refused(self, message, *extra, code=1, **kwargs):
        result, _, err = run_cli(
            cli_args(self.mirror, self.output, *extra, **kwargs)
        )
        self.assertEqual(result, code, err)
        self.assertIn(message, err)
        self.assertFalse(self.output.exists())


class FixtureTest(unittest.TestCase):

    def test_committed_fixtures_match_the_generator(self):
        expected = fx.build_objects()
        committed = {
            str(p.relative_to(fx.FIXTURE_ROOT)): p.read_bytes()
            for p in fx.FIXTURE_ROOT.rglob("*")
            if p.is_file()
        }
        self.assertEqual(committed, expected)

    def test_fixtures_are_synthetic(self):
        for name, data in fx.build_objects().items():
            if "/requests/" in name:
                facts = json.loads(data)["request"]
                request_id = facts["provider_request_id"]
                self.assertTrue(
                    request_id is None or request_id.startswith("synthetic-")
                )


class SummaryTest(MirrorTestCase):

    @fakes.no_network
    def test_cli_with_slot_evidence(self):
        with mock.patch.object(
            obj, "GcsObjectStore", side_effect=AssertionError("no GCS")
        ):
            code, out, err = run_cli(
                cli_args(
                    self.mirror, self.output, "--collector-policy-start", POLICY
                )
            )
        self.assertEqual(code, 0, err)
        self.assertIn("Wrote", out)
        data = self.output.read_bytes()
        summary = json.loads(data)
        self.assertEqual(summary["schema_version"], "llm-metrics.analytics.v1")
        # Failure stays in the denominator; missing/unrecorded slots do not.
        self.assertEqual(
            {
                k: summary["reliability"][k]
                for k in ("attempts", "successes", "failures")
            },
            {"attempts": 6, "successes": 5, "failures": 1},
        )
        self.assertEqual(
            summary["reliability"]["failures_by_category"]["provider_error"], 1
        )
        self.assertEqual(
            summary["slot_completeness"]["states"],
            {
                "recorded_success": 5,
                "recorded_failure": 1,
                "claim_without_record": 1,
                "missing": 1,
            },
        )
        self.assertEqual(summary["slot_completeness"]["expected_slots"], 8)
        ttft = summary["metrics"]["ttft"]
        # Successes only, nearest rank: sorted 1420, 1510, 1650.25, 1880.5,
        # 2210.75 -> p50 rank 3, p95 rank 5.
        self.assertEqual(
            (ttft["count"], ttft["min"], ttft["p50"], ttft["p95"], ttft["max"]),
            (5, 1420.0, 1650.25, 2210.75, 2210.75),
        )
        self.assertEqual(ttft["latest"]["attempt_id"], fx.attempt_id(7))
        rate = summary["metrics"]["output_tokens_per_s"]
        self.assertEqual(
            (rate["count"], rate["successes_without_value"]), (4, 1)
        )
        self.assertEqual(rate["p50"], 108.25)
        cost = summary["cost_usd"]
        self.assertEqual(cost["priced_successes"], 5)
        self.assertEqual(cost["failed_attempts_cost_unknown"], 1)
        self.assertAlmostEqual(cost["known_total_cost"], 0.0003045)
        self.assertEqual(summary["tokens"]["input_tokens"], 260)
        self.assertEqual(
            summary["tokens"]["cached_input_tokens_unknown_count"], 1
        )
        self.assertEqual(
            summary["source"]["excluded_by_filter"],
            {"other_workload": 1, "outside_time_window": 1},
        )
        self.assertEqual(
            summary["provenance"]["records_without_provider_request_id"], 2
        )
        codes = [c["code"] for c in summary["caveats"]]
        self.assertIn("slots_without_records", codes)
        self.assertIn("p95_is_sample_max", codes)
        self.assertNotIn("no_slot_evidence", codes)
        # Never published: provider request ids, test records, CSV backups.
        text = data.decode()
        self.assertNotIn("synthetic-req", text)
        self.assertNotIn(fx.attempt_id(92), text)
        self.assertNotIn("snapshots", text)
        self.assertEqual(ra.encode_summary(summary), data)  # canonical

    def test_output_is_byte_identical_and_create_only(self):
        args = cli_args(
            self.mirror, self.output, "--collector-policy-start", POLICY
        )
        self.assertEqual(run_cli(args)[0], 0)
        first = self.output.read_bytes()
        code, out, _ = run_cli(args)
        self.assertEqual(code, 0)
        self.assertIn("Unchanged", out)
        self.assertEqual(self.output.read_bytes(), first)
        other = self.tmp / "out" / "again.json"
        self.assertEqual(
            run_cli(
                cli_args(self.mirror, other, "--collector-policy-start", POLICY)
            )[0],
            0,
        )
        self.assertEqual(other.read_bytes(), first)
        self.assertEqual(
            sorted(p.name for p in self.output.parent.iterdir()),
            ["again.json", "summary.json"],
        )

    def test_evidence_manifest_matches_the_files(self):
        summary = self.build()
        lines = ""
        for entry in summary["evidence"]["records"]:
            data = (self.mirror / entry["object_name"]).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), entry["sha256"])
            lines += f"{entry['sha256']}  {entry['object_name']}\n"
        self.assertEqual(
            hashlib.sha256(lines.encode()).hexdigest(),
            summary["evidence"]["manifest_sha256"],
        )
        self.assertEqual(summary["evidence"]["record_count"], 6)

    def test_records_only_reports_no_slot_completeness(self):
        summary = self.build(policy_start=None)
        self.assertIsNone(summary["slot_completeness"])
        self.assertIn(
            "no_slot_evidence", [c["code"] for c in summary["caveats"]]
        )
        self.assertEqual(summary["reliability"]["attempts"], 6)

    def test_one_off_population_is_separate(self):
        summary = self.build(
            policy_start=None,
            start=datetime.datetime(2026, 1, 5, 17, 0, tzinfo=UTC),
            end=datetime.datetime(2026, 1, 5, 18, 0, tzinfo=UTC),
        )
        self.assertEqual(
            summary["evidence"]["records"][0]["attempt_id"], fx.attempt_id(90)
        )
        self.assertEqual(summary["reliability"]["attempts"], 1)

    def test_only_failures_gives_nulls_not_zeros(self):
        summary = self.build(
            policy_start=None,
            start=datetime.datetime(2026, 1, 5, 18, 30, tzinfo=UTC),
            end=datetime.datetime(2026, 1, 5, 18, 45, tzinfo=UTC),
        )
        self.assertEqual(summary["reliability"]["successes"], 0)
        for metric in summary["metrics"].values():
            self.assertEqual(metric["count"], 0)
            self.assertIsNone(metric["p50"])
            self.assertIsNone(metric["latest"])
        self.assertIsNone(summary["cost_usd"]["known_total_cost"])
        self.assertIsNone(summary["tokens"]["input_tokens"])

    def test_non_finite_values_are_refused(self):
        with self.assertRaises(ra.AnalyticsInputError):
            ra.encode_summary({"value": float("nan")})


class InputRefusalTest(MirrorTestCase):

    def test_zero_matching_records(self):
        self.assert_refused("No records match", end="2026-01-05T18:00:05Z")

    def test_other_region_matches_nothing(self):
        args = cli_args(self.mirror, self.output)
        args[args.index("gcp/us-central1")] = "gcp/europe-west1"
        code, _, err = run_cli(args)
        self.assertEqual(code, 1)
        self.assertIn("No records match", err)

    def test_missing_input(self):
        shutil.rmtree(self.mirror)
        self.assert_refused("not a directory")

    def test_malformed_json(self):
        (self.mirror / DAY_DIR / fx.attempt_id(4)).with_suffix(
            ".json"
        ).write_bytes(b"{nope")
        self.assert_refused("not UTF-8 JSON")

    def test_non_canonical_record(self):
        path = self.mirror / DAY_DIR / f"{fx.attempt_id(4)}.json"
        path.write_text(json.dumps(json.loads(path.read_bytes()), indent=2))
        self.assert_refused("canonical form")

    def test_invalid_schema(self):
        path = self.mirror / DAY_DIR / f"{fx.attempt_id(4)}.json"
        record = json.loads(path.read_bytes())
        record["request"]["input_tokens"] = None  # success with unknown tokens
        path.write_bytes(
            json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
        )
        self.assert_refused("input_tokens must be known")

    def test_misplaced_record(self):
        source = self.mirror / DAY_DIR / f"{fx.attempt_id(4)}.json"
        source.rename(self.mirror / DAY_DIR / f"{fx.attempt_id(44)}.json")
        self.assert_refused("does not belong under its object name")

    def test_test_record_in_prod_directory(self):
        test_dir = self.mirror / "attempts/v1/requests/test/2026-01-05"
        name = f"{fx.attempt_id(92)}.json"
        shutil.copy(test_dir / name, self.mirror / DAY_DIR / name)
        self.assert_refused("does not belong under its object name")

    def test_corrupted_bytes_of_a_valid_record(self):
        path = self.mirror / DAY_DIR / f"{fx.attempt_id(5)}.json"
        path.write_bytes(path.read_bytes()[:-1])
        self.assert_refused("Invalid record")

    def test_oversized_file(self):
        path = self.mirror / DAY_DIR / f"{fx.attempt_id(4)}.json"
        path.write_bytes(b" " * (ra.MAX_RECORD_BYTES + 1))
        self.assert_refused("too large")

    def test_unexpected_entries(self):
        (self.mirror / DAY_DIR / "notes.txt").write_text("x")
        self.assert_refused("Not a record file")
        (self.mirror / DAY_DIR / "notes.txt").unlink()
        (self.mirror / "attempts/v1/requests/prod/latest").mkdir()
        self.assert_refused("Unexpected entry")

    def test_symlinked_record_and_directory(self):
        outside = self.tmp / "outside.json"
        shutil.copy(self.mirror / DAY_DIR / f"{fx.attempt_id(4)}.json", outside)
        (self.mirror / DAY_DIR / f"{fx.attempt_id(4)}.json").unlink()
        os.symlink(outside, self.mirror / DAY_DIR / f"{fx.attempt_id(4)}.json")
        self.assert_refused("symlink")
        (self.mirror / DAY_DIR / f"{fx.attempt_id(4)}.json").unlink()
        os.symlink(
            self.tmp, self.mirror / "attempts/v1/requests/prod/2026-01-06"
        )
        self.assert_refused("symlink")

    def test_unsafe_prefix(self):
        self.assert_refused("prefix", "--prefix", "../attempts")

    def test_duplicate_provider_request_id(self):
        moment = datetime.datetime(2026, 1, 5, 18, 50, tzinfo=UTC)
        (self.mirror / DAY_DIR / f"{fx.attempt_id(60)}.json").write_bytes(
            record_bytes(60, moment, provider_request_id="synthetic-req-0004")
        )
        self.assert_refused("Duplicate provider request id")

    def test_mixed_provider_model_under_selected_profile(self):
        moment = datetime.datetime(2026, 1, 5, 18, 50, tzinfo=UTC)
        (self.mirror / DAY_DIR / f"{fx.attempt_id(61)}.json").write_bytes(
            record_bytes(61, moment, model="gpt-6-sol")
        )
        self.assert_refused("Mixed population")

    def test_unclaimed_record_with_slot_evidence(self):
        moment = datetime.datetime(2026, 1, 5, 18, 50, tzinfo=UTC)
        (self.mirror / DAY_DIR / f"{fx.attempt_id(62)}.json").write_bytes(
            record_bytes(62, moment)
        )
        self.assert_refused(
            "Mixed population", "--collector-policy-start", POLICY
        )
        # Without slot evidence the same record is simply part of the window.
        self.assertEqual(
            self.build(policy_start=None)["reliability"]["attempts"], 7
        )

    def test_window_that_cuts_a_slot_record(self):
        self.assert_refused(
            "disagree", "--collector-policy-start", POLICY,
            end="2026-01-05T18:15:06Z",
        )  # fmt: skip

    def test_slot_evidence_requires_collector_scope_and_start(self):
        with self.assertRaisesRegex(ra.AnalyticsInputError, "scope"):
            self.build(workload_id="long-output-v1")
        with self.assertRaisesRegex(ra.AnalyticsInputError, "policy start"):
            self.build(start=datetime.datetime(2026, 1, 5, 18, 15, tzinfo=UTC))
        with self.assertRaisesRegex(ra.AnalyticsInputError, "quarter-hour"):
            self.build(
                policy_start=datetime.datetime(2026, 1, 5, 18, 5, tzinfo=UTC)
            )


class OutputRefusalTest(MirrorTestCase):

    def test_existing_different_file_is_kept(self):
        self.output.write_bytes(b"old")
        self.assert_refused_keep(b"old", "different content")

    def assert_refused_keep(self, content, message):
        code, _, err = run_cli(cli_args(self.mirror, self.output))
        self.assertEqual(code, 1)
        self.assertIn(message, err)
        self.assertEqual(self.output.read_bytes(), content)
        self.assertEqual(list(self.output.parent.iterdir()), [self.output])

    def test_output_inside_mirror(self):
        code, _, err = run_cli(
            cli_args(self.mirror, self.mirror / "summary.json")
        )
        self.assertEqual(code, 1)
        self.assertIn("inside the input mirror", err)
        self.assertFalse((self.mirror / "summary.json").exists())

    def test_output_symlink_and_missing_directory(self):
        os.symlink(self.tmp / "elsewhere.json", self.output)
        code, _, err = run_cli(cli_args(self.mirror, self.output))
        self.assertEqual(code, 1)
        self.assertIn("symlink", err)
        self.assertFalse((self.tmp / "elsewhere.json").exists())
        code, _, err = run_cli(
            cli_args(self.mirror, self.tmp / "no" / "s.json")
        )
        self.assertEqual((code, "does not exist" in err), (1, True))


class ArgumentTest(MirrorTestCase):

    def test_bad_arguments_exit_2(self):
        self.assertEqual(run_cli(["--input", str(self.mirror)])[0], 2)
        self.assertEqual(
            run_cli(cli_args(self.mirror, self.output, end="tomorrow"))[0], 2
        )
        self.assertEqual(
            run_cli(
                cli_args(self.mirror, self.output, end="2026-01-05T18:00:00Z")
            )[0],
            2,
        )
        args = cli_args(self.mirror, self.output)
        args[args.index("gcp/us-central1")] = "us-central1"
        self.assertEqual(run_cli(args)[0], 2)
        args = cli_args(self.mirror, self.output)
        args[args.index("gpt-6-luna")] = "gpt-6-sol"
        self.assertEqual(run_cli(args)[0], 2)
        self.assertEqual(
            run_cli([*cli_args(self.mirror, self.output), "--bucket", "b"])[0],
            2,
        )
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
