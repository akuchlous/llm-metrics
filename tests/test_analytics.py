"""Tests for `llm_metrics.analytics`: natural-value results, no web layer.

Each test uses its own temporary database. Nothing here imports Flask or
Jinja; a separate test checks that importing analytics does not load them.
"""

import datetime
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

from llm_metrics import analytics
from llm_metrics import storage

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
NOW = datetime.datetime(2026, 11, 30, 12, 0, tzinfo=datetime.timezone.utc)
DUMMY = {"provider": "dummy", "model": "dummy-model-v1"}
ATTEMPT = {
    **DUMMY,
    "workload_id": "simulated.default.v1",
    "origin_cloud": "local",
    "origin_region": "unknown",
    "cache_policy": "provider_default",
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
FAILED_ATTEMPT = {
    **ATTEMPT,
    "outcome": "timeout",
    "input_tokens": None,
    "output_tokens": None,
    "input_cost": None,
    "output_cost": None,
    "total_cost": None,
    "failed_after_ms": 60000.0,
}


def observation(hours_ago, value):
    return analytics.Observation(
        NOW - datetime.timedelta(hours=hours_ago), value
    )


class AnalyticsTestCase(unittest.TestCase):
    """Gives each test its own temporary database at `self.db_path`."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db_path = pathlib.Path(tmp.name) / "analytics.db"

    def save_observation(self, hours_ago, value, metric="ttft", env="test"):
        storage.save_new_observations(
            self.db_path,
            [
                (
                    NOW - datetime.timedelta(hours=hours_ago),
                    {**DUMMY, "metric": metric, "value": value},
                )
            ],
            env,
        )

    def metric_window(self, metric="ttft", env="test", hours=24):
        start, end = analytics.window_bounds(
            datetime.timedelta(hours=hours), NOW
        )
        return analytics.load_metric_window(
            self.db_path,
            env,
            "dummy",
            "dummy-model-v1",
            metric,
            start=start,
            end=end,
        )


class WindowBoundsTest(unittest.TestCase):

    def test_window_ends_now_and_spans_the_duration(self):
        self.assertEqual(
            analytics.window_bounds(datetime.timedelta(days=7), NOW),
            (NOW - datetime.timedelta(days=7), NOW),
        )

    def test_recorded_at_is_parsed_to_aware_utc(self):
        moment = analytics.parse_recorded_at("2026-10-30T12:34:56.789012Z")
        self.assertEqual(
            moment,
            datetime.datetime(
                2026, 10, 30, 12, 34, 56, 789012, tzinfo=datetime.timezone.utc
            ),
        )


class MetricSummaryTest(unittest.TestCase):

    def test_empty_population_has_no_summary(self):
        self.assertIsNone(analytics.summarize_metric([]))

    def test_nearest_rank_percentiles_and_natural_values(self):
        observations = [
            observation(10 - i, value)
            for i, value in enumerate([5.0, 1.0, 4.0, 2.0, 3.0])
        ]
        summary = analytics.summarize_metric(observations)
        self.assertEqual(summary.count, 5)
        self.assertEqual(summary.latest_value, 3.0)
        self.assertEqual(summary.latest_at, observations[-1].recorded_at)
        self.assertEqual(summary.first_at, observations[0].recorded_at)
        # Nearest rank over sorted [1, 2, 3, 4, 5]: ceil(p * 5 / 100).
        self.assertEqual(summary.percentiles, {50: 3.0, 95: 5.0, 99: 5.0})
        # Natural values, not display strings.
        self.assertIsInstance(summary.latest_value, float)
        self.assertIsInstance(summary.latest_at, datetime.datetime)
        for value in summary.percentiles.values():
            self.assertIsInstance(value, float)

    def test_single_observation_is_every_percentile(self):
        summary = analytics.summarize_metric([observation(1, 101.0)])
        self.assertEqual(summary.percentiles, {50: 101.0, 95: 101.0, 99: 101.0})


class MetricWindowTest(AnalyticsTestCase):

    def test_reliability_counts_failures_but_percentiles_exclude_them(self):
        for hours_ago, value in ((3, 100.0), (2, 200.0)):
            self.save_observation(hours_ago, value)
        storage.save_request(self.db_path, ATTEMPT, [], "test")
        for _ in range(3):
            storage.save_request(self.db_path, FAILED_ATTEMPT, [], "test")
        # Attempts are saved with the real clock, observations relative to the
        # fixed NOW; a 40-day window ending at NOW contains both.
        result = self.metric_window(hours=24 * 40)
        # All 4 attempts count for reliability, 3 of them failed...
        self.assertEqual(result.reliability["attempts"], 4)
        self.assertEqual(result.reliability["failures"], 3)
        self.assertEqual(
            result.reliability["failures_by_category"]["timeout"], 3
        )
        self.assertAlmostEqual(result.reliability["success_rate"], 0.25)
        # ...but the distribution holds only the 2 successful observations: no
        # fabricated zero latencies for the failures.
        self.assertEqual([o.value for o in result.observations], [100.0, 200.0])
        self.assertEqual(result.summary.count, 2)
        self.assertNotIn(0.0, result.summary.percentiles.values())

    def test_empty_window_is_well_defined(self):
        result = self.metric_window()
        self.assertEqual(result.observations, ())
        self.assertIsNone(result.summary)
        self.assertIsNone(result.reliability)  # no attempts: no rate, not 0%
        self.assertEqual(
            result.end - result.start, datetime.timedelta(hours=24)
        )

    def test_window_and_population_filter(self):
        self.save_observation(1, 1.0)
        self.save_observation(30, 2.0)  # outside 24h
        self.save_observation(1, 3.0, metric="total_latency")  # other metric
        self.save_observation(2, 4.0, env="prod")  # other population
        result = self.metric_window()
        self.assertEqual([o.value for o in result.observations], [1.0])
        self.assertEqual(
            [o.value for o in self.metric_window(env="prod").observations],
            [4.0],
        )

    def test_observations_carry_aware_datetimes(self):
        self.save_observation(1, 1.0)
        [only] = self.metric_window().observations
        self.assertEqual(only.recorded_at, NOW - datetime.timedelta(hours=1))
        self.assertIsNotNone(only.recorded_at.tzinfo)


class RecentAttemptsTest(AnalyticsTestCase):

    def test_populations_stay_separate_and_unknowns_stay_none(self):
        simulated_id = storage.save_request(
            self.db_path, FAILED_ATTEMPT, [], "test"
        )
        real_id = storage.save_request(self.db_path, ATTEMPT, [], "prod")
        simulated = analytics.load_recent_attempts(self.db_path, "test", 20)
        real = analytics.load_recent_attempts(self.db_path, "prod", 20)
        self.assertEqual([a["id"] for a in simulated], [simulated_id])
        self.assertEqual([a["id"] for a in real], [real_id])
        attempt = simulated[0]
        self.assertIsInstance(attempt["recorded_at"], datetime.datetime)
        # Unknown facts stay None (never 0 or "—" at this layer).
        for key in ("input_tokens", "output_tokens", "total_cost"):
            self.assertIsNone(attempt[key])
        self.assertIsNone(attempt["cached_input_tokens"])
        self.assertEqual(attempt["failed_after_ms"], 60000.0)


def spend_group(successful_calls, failed_attempts, cost, tokens=10):
    return {
        "provider": "openai",
        "model": "m",
        "attempts": successful_calls + failed_attempts,
        "successful_calls": successful_calls,
        "failed_attempts": failed_attempts,
        "input_tokens": tokens if successful_calls else None,
        "output_tokens": tokens if successful_calls else None,
        "total_cost": cost,
    }


class SpendTest(AnalyticsTestCase):

    def test_totals_sum_known_costs_and_count_failures(self):
        totals = analytics.spend_totals(
            [spend_group(2, 0, 0.00003), spend_group(0, 1, None)]
        )
        self.assertEqual(totals.successful_calls, 2)
        self.assertEqual(totals.failed_attempts, 1)
        self.assertEqual((totals.input_tokens, totals.output_tokens), (10, 10))
        self.assertAlmostEqual(totals.total_cost, 0.00003)

    def test_unknown_cost_is_none_never_zero(self):
        totals = analytics.spend_totals([spend_group(0, 2, None)])
        self.assertIsNone(totals.total_cost)
        self.assertIsNone(analytics.spend_totals([]))

    def test_benchmark_spend_is_real_data_only(self):
        storage.save_request(self.db_path, ATTEMPT, [], "test")  # simulated
        real = {**ATTEMPT, "provider": "openai", "model": "gpt-6-luna"}
        storage.save_request(self.db_path, real, [], "prod")
        storage.save_request(
            self.db_path,
            {**FAILED_ATTEMPT, "provider": "openai", "model": "gpt-6-luna"},
            [],
            "prod",
        )
        spend = analytics.load_benchmark_spend(
            self.db_path,
            start=datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(days=1),
            end=datetime.datetime.now(datetime.timezone.utc),
        )
        self.assertEqual(
            [(g["provider"], g["model"]) for g in spend.groups],
            [("openai", "gpt-6-luna")],
        )
        self.assertEqual(spend.totals.successful_calls, 1)
        self.assertEqual(spend.totals.failed_attempts, 1)
        self.assertAlmostEqual(spend.totals.total_cost, 6.2e-05)
        self.assertIsInstance(spend.totals.total_cost, float)

    def test_empty_spend_window(self):
        spend = analytics.load_benchmark_spend(
            self.db_path, start=NOW - datetime.timedelta(days=30), end=NOW
        )
        self.assertEqual(spend.groups, ())
        self.assertIsNone(spend.totals)


class IndependenceTest(unittest.TestCase):

    def test_analytics_loads_without_any_web_package(self):
        code = (
            "import sys\n"
            "import llm_metrics.analytics\n"
            "web = ('flask', 'werkzeug', 'jinja2', 'markupsafe')\n"
            "print(sorted(m for m in sys.modules if m.split('.')[0] in web))\n"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=REPO_ROOT,
            env=dict(os.environ),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "[]")


if __name__ == "__main__":
    unittest.main()
