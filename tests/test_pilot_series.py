"""Step 027c: per-slot series, chart rendering, and the plan-only pilot."""

# pylint: disable=protected-access

import datetime
import json
import pathlib
import re
import tempfile
import unittest

from llm_metrics import pilot_plan as pp
from llm_metrics import pilot_series as ps
from llm_metrics import record_analytics as ra
from llm_metrics import scheduled_collector as sc
from llm_metrics import static_site as ss
from tests import analytics_fixtures as fx
from tests import test_record_analytics as tra
from tests import test_static_site as t25

STAGING = ss.SiteConfig("https://llmxchange.example.workers.dev")
UTC = datetime.timezone.utc


def series_bytes(**overrides) -> bytes:
    return ps.build(fx.FIXTURE_ROOT, "attempts", tra.population(**overrides))


def loaded(data: bytes | None = None, dataset=None):
    dataset = dataset or t25.dataset(t25.summary_bytes())
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "series.json"
        path.write_bytes(series_bytes() if data is None else data)
        return ss.load_series(path, dataset), dataset


class SeriesTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.data = series_bytes()
        cls.series = json.loads(cls.data)

    def test_one_row_per_policy_slot_with_states(self):
        rows = self.series["slots"]
        self.assertEqual(len(rows), sc.MAX_SLOTS)
        self.assertEqual(rows[0]["slot"], "2026-01-05T18:00:00Z")
        self.assertEqual(
            self.series["counts"],
            {
                "success": 5,
                "failure": 1,
                "missing": 1,
                "claim_without_record": 1,
                "not_due": 88,
            },
        )
        states = {r["slot"][11:16]: r["state"] for r in rows[:9]}
        self.assertEqual(states["18:30"], "failure")
        self.assertEqual(states["19:15"], "missing")
        self.assertEqual(states["19:30"], "claim_without_record")
        self.assertEqual(states["20:00"], "not_due")  # cutoff is exclusive

    def test_values_are_rounded_per_request_and_unknown_is_null(self):
        rows = {r["slot"][11:16]: r for r in self.series["slots"]}
        self.assertIsNone(rows["19:00"]["output_tokens_per_s"])
        for row in self.series["slots"]:
            for key in ("ttft_ms", "total_latency_ms", "output_tokens_per_s"):
                value = row.get(key)
                if value is not None:
                    self.assertEqual(value, round(value, 1))
        self.assertEqual(rows["18:30"]["failure_category"], "provider_error")
        self.assertNotIn("ttft_ms", rows["18:30"])

    def test_no_ids_or_object_names_and_same_evidence_as_analytics(self):
        self.assertNotIn(b"attempt", self.data)
        self.assertNotIn(b"attempts/v1", self.data)
        self.assertNotIn(b"synthetic-", self.data)
        summary = json.loads(t25.summary_bytes())
        self.assertEqual(
            self.series["record_manifest_sha256"],
            summary["evidence"]["manifest_sha256"],
        )
        self.assertEqual(ra.encode_summary(self.series), self.data)

    def test_end_beyond_the_policy_is_refused(self):
        with self.assertRaises(ra.AnalyticsInputError):
            series_bytes(end=fx.POLICY_START + sc.WINDOW * 2)


class LoadSeriesTest(unittest.TestCase):

    def edited(self, change):
        series = json.loads(series_bytes())
        change(series)
        return ra.encode_summary(series)

    def test_valid_series_loads(self):
        series, _ = loaded()
        self.assertTrue(series.json_path.startswith("/data/series/"))

    def test_refusals(self):
        def other_manifest(s):
            s["record_manifest_sha256"] = "0" * 64

        def extra_field(s):
            s["slots"][0]["attempt_id"] = "x"

        def future_as_success(s):
            s["slots"][-1] = {
                "slot": s["slots"][-1]["slot"],
                "state": "success",
                "ttft_ms": 1.0,
                "total_latency_ms": 2.0,
                "output_tokens_per_s": 3.0,
            }

        def wrong_count(s):
            s["counts"]["success"] += 1

        def reordered(s):
            s["slots"][0], s["slots"][1] = s["slots"][1], s["slots"][0]

        for change in (
            other_manifest,
            extra_field,
            future_as_success,
            wrong_count,
            reordered,
        ):
            with self.subTest(change.__name__):
                with self.assertRaises(ss.SiteError):
                    loaded(self.edited(change))

    def test_non_canonical_bytes_refused(self):
        data = json.dumps(json.loads(series_bytes()), indent=2).encode()
        with self.assertRaisesRegex(ss.SiteError, "canonical"):
            loaded(data)


class ChartTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        series, dataset = loaded()
        cls.view = ss.series_view(series, dataset)
        cls.files = ss.render_site(t25.CONFIG, dataset, series=series)
        cls.page = cls.files[t25.METRIC].decode()

    def test_lines_break_at_failed_missing_and_future_slots(self):
        ttft = self.view["charts"][0]
        # Successes at 18:00, 18:15 | fail | 18:45, 19:00 | missing,
        # claim-without-record | 19:45: segments of 2 and 2 points.
        self.assertEqual([len(s.split()) for s in ttft["segments"]], [2, 2])
        self.assertEqual(len(ttft["points"]) + len(ttft["clipped"]), 5)
        self.assertEqual(
            sorted(m["state"] for m in ttft["marks"]),
            ["claim_without_record", "failure", "missing"],
        )
        self.assertIsNotNone(ttft["future"])
        throughput = self.view["charts"][2]
        self.assertEqual(throughput["n"], 4)  # one success has no value
        self.assertEqual(throughput["missing_values"], 1)

    def test_page_labels_per_request_observations_and_is_static(self):
        self.assertIn("Each dot is <strong>one request</strong>", self.page)
        self.assertNotIn("hourly average", self.page.lower())
        self.assertNotIn("percentile trend", self.page.lower())
        self.assertEqual(self.page.count('<svg class="chart timeseries"'), 3)
        self.assertIn('<svg class="chart outcomes"', self.page)
        self.assertIn("Not yet due: <strong>88</strong>", self.page)
        self.assertIn("nearest-rank", self.page)
        for svg in re.findall(r"<svg class=\"chart [^>]*>.*?</svg>", self.page,
                              re.S):  # fmt: skip
            self.assertIn('role="img"', svg)
            self.assertIn("<title", svg)
            self.assertIn("<desc", svg)
            self.assertNotIn("style=", svg)
            self.assertNotIn("<script", svg)
        self.assertIn("<details>", self.page)
        self.assertEqual(
            self.page.count('<tr><th scope="row"><time'), sc.MAX_SLOTS
        )
        name = self.view["json_path"][1:]
        self.assertEqual(self.files[name], series_bytes())

    def test_outliers_are_capped_and_labelled_not_hidden(self):
        rows = [
            {"slot": f"s{i}", "state": "success", "ttft_ms": v}
            for i, v in enumerate([100.0, 120.0, 110.0, 5000.0])
        ]
        for row in rows:
            row["slot"] = "2026-01-05T18:00:00Z"
        chart = ss._line_chart(
            rows, "ttft_ms", "ms", "TTFT", {"p50": 110.0, "p95": 120.0}
        )
        self.assertEqual(len(chart["clipped"]), 1)
        self.assertEqual(chart["clipped"][0]["label"], "5,000 ms")
        self.assertEqual(chart["axis_top"], "250 ms")

    def test_nice_axis(self):
        self.assertEqual(ss._nice_max(5102), 6000)
        self.assertEqual(ss._nice_max(11834), 15000)
        self.assertEqual(ss._nice_max(0), 1.0)

    def test_series_requires_a_dataset(self):
        series, _ = loaded()
        with self.assertRaisesRegex(ss.SiteError, "dataset"):
            ss.render_site(t25.CONFIG, None, series=series)


NOW = datetime.datetime(2026, 11, 8, 3, 0, tzinfo=UTC)
CLOSED = [
    {
        "run_id": "openai.gpt-6-luna.v1/2026-11-06T18:00:00Z",
        "start": "2026-11-06T18:00:00Z",
        "expires": "2026-11-07T18:00:00Z",
        "closed": True,
    }
]


class PlanTest(unittest.TestCase):

    def start(self, text):
        return pp.parse(text)

    def test_plan_is_bounded_and_identified(self):
        result = pp.plan(self.start("2026-11-08T12:00:00Z"), NOW, CLOSED)
        self.assertTrue(result["plan_only"])
        self.assertEqual(len(result["slot_times"]), 96)
        self.assertEqual(result["window"]["expires"], "2026-11-09T12:00:00Z")
        self.assertEqual(
            result["run_id"], "openai.gpt-6-luna.v1/2026-11-08T12:00:00Z"
        )
        launch = result["commands"]["launch_after_approval_c"]
        self.assertIn("activate 2026-11-08T12:00:00Z", launch)
        self.assertEqual(result["cost"]["max_paid_requests"], 96)

    def test_refusals(self):
        cases = {
            "2026-11-08T12:10:00Z": "quarter hour",
            "2026-11-08T03:15:00Z": "30 minutes",
            "2026-11-08T02:00:00Z": "30 minutes",
            "2026-11-30T12:00:00Z": "14 days",
            "2026-11-07T18:00:00Z": "30 minutes",
        }
        for text, message in cases.items():
            with self.subTest(text):
                with self.assertRaisesRegex(pp.PlanError, message):
                    pp.plan(self.start(text), NOW, CLOSED)

    def test_overlap_duplicate_and_open_previous_run(self):
        early = datetime.datetime(2026, 11, 5, 0, 0, tzinfo=UTC)
        with self.assertRaisesRegex(pp.PlanError, "overlaps"):
            pp.plan(self.start("2026-11-07T12:00:00Z"), early, CLOSED)
        with self.assertRaisesRegex(pp.PlanError, "already used"):
            pp.plan(self.start("2026-11-06T18:00:00Z"), early, CLOSED)
        # Adjacent but within the late-record limit is an overlap too.
        with self.assertRaisesRegex(pp.PlanError, "overlaps"):
            pp.plan(self.start("2026-11-07T18:00:00Z"), early, CLOSED)
        open_run = [{**CLOSED[0], "closed": False}]
        with self.assertRaisesRegex(pp.PlanError, "not closed"):
            pp.plan(self.start("2026-11-08T12:00:00Z"), NOW, open_run)

    def test_runs_partition_by_policy_window(self):
        first = sc.Policy(
            *(
                pp.parse(r)
                for r in ("2026-11-06T18:00:00Z", "2026-11-07T18:00:00Z")
            )
        )
        second = sc.Policy(pp.parse("2026-11-08T12:00:00Z"),
                           pp.parse("2026-11-09T12:00:00Z"))  # fmt: skip
        self.assertFalse(set(first.slots()) & set(second.slots()))
        self.assertNotEqual(pp.run_id(first.start), pp.run_id(second.start))

    def test_cost_estimate_from_a_summary(self):
        summary = json.loads(t25.summary_bytes())
        cost = pp.cost_estimate(summary)
        self.assertIsNotNone(cost["expected_usd"])
        self.assertGreaterEqual(cost["upper_bound_usd"], cost["expected_usd"])
        self.assertIn("not billing", cost["basis"])
        self.assertIsNone(pp.cost_estimate(None)["expected_usd"])

    def test_execute_is_refused_and_no_cloud_commands_run(self):
        self.assertEqual(
            pp.main(["--start", "2026-11-08T12:00:00Z", "--execute"]), 1
        )
        source = pathlib.Path(pp.__file__).read_text("utf-8")
        for forbidden in ("subprocess", "os.system", "urllib", "requests",
                          "google.cloud", "openai"):  # fmt: skip
            self.assertNotIn(f"import {forbidden}", source)

    def test_committed_registry_is_valid(self):
        runs = pp.load_runs(pp.RUNS_PATH) if pp.RUNS_PATH.exists() else []
        for run in runs:
            self.assertEqual(run["run_id"], pp.run_id(pp.parse(run["start"])))


if __name__ == "__main__":
    unittest.main()
