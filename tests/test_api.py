"""Tests for the JSON API: `llm_metrics.api` and `GET /api/v1/metrics`.

`SerializerTest` exercises `api` directly, without Flask. `MetricsEndpointTest`
goes through Flask's test client against a temporary database with a fixed
clock and outgoing network access blocked, so no test can reach a provider.
"""

import ast
import contextlib
import datetime
import json
import os
import pathlib
import re
import tempfile
import unittest
from unittest import mock

from llm_metrics import analytics
from llm_metrics import api
from llm_metrics import query
from llm_metrics import storage
from llm_metrics import web

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
NOW = datetime.datetime(2026, 11, 30, 12, 0, tzinfo=datetime.timezone.utc)
ISO_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")
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
    "outcome": "rate_limited",
    "input_tokens": None,
    "output_tokens": None,
    "input_cost": None,
    "output_cost": None,
    "total_cost": None,
    "failed_after_ms": 1500.0,
}
# Every key a v1 metrics body has, at each level: the compatibility contract.
TOP_LEVEL_KEYS = [
    "api_version",
    "population",
    "metric",
    "window",
    "samples",
    "reliability",
]
RELIABILITY_KEYS = [
    "attempts",
    "successes",
    "failures",
    "success_rate",
    "failure_rate",
    "failures_by_category",
]


def timestamps(body):
    """Returns every time field of a metrics body that is not None."""
    samples = body["samples"]
    found = [body["window"]["start"], body["window"]["end"]]
    if samples["latest"] is not None:
        found += [
            samples["first_recorded_at"],
            samples["latest"]["recorded_at"],
        ]
    return found


def numbers_only(value):
    """True if `value` holds no strings below dict keys (None is allowed)."""
    if isinstance(value, dict):
        return all(numbers_only(v) for v in value.values())
    return value is None or (
        isinstance(value, (int, float)) and not isinstance(value, bool)
    )


class SerializerTest(unittest.TestCase):
    """`api` on hand-built analytics results: no Flask, no database."""

    def window(self, observations=(), reliability=None):
        observations = tuple(observations)
        return analytics.MetricWindow(
            start=NOW - datetime.timedelta(days=7),
            end=NOW,
            observations=observations,
            summary=analytics.summarize_metric(observations),
            reliability=reliability,
        )

    def test_timestamp_is_iso_8601_utc_with_microseconds(self):
        self.assertEqual(api.timestamp(NOW), "2026-11-30T12:00:00.000000Z")
        india = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
        moment = datetime.datetime(2026, 11, 30, 17, 30, 0, 5, tzinfo=india)
        self.assertEqual(api.timestamp(moment), "2026-11-30T12:00:00.000005Z")

    def test_body_shape_identifies_population_metric_and_window(self):
        body = api.metrics_response(self.window(), "7d", "total_latency")
        self.assertEqual(list(body), TOP_LEVEL_KEYS)
        self.assertEqual(body["api_version"], "v1")
        self.assertEqual(
            body["population"],
            {
                "data": "simulated",
                "provider": "dummy",
                "model": "dummy-model-v1",
            },
        )
        self.assertEqual(
            body["metric"], {"name": "total_latency", "unit": "ms"}
        )
        self.assertEqual(
            body["window"],
            {
                "name": "7d",
                "start": "2026-11-23T12:00:00.000000Z",
                "end": "2026-11-30T12:00:00.000000Z",
            },
        )

    def test_units_come_from_the_metric_catalogue(self):
        for name, (_, unit) in query.METRICS.items():
            with self.subTest(metric=name):
                body = api.metrics_response(self.window(), "24h", name)
                self.assertEqual(body["metric"]["unit"], unit)

    def test_empty_window_has_nulls_and_true_zero_counts(self):
        body = api.metrics_response(self.window(), "7d", "ttft")
        self.assertEqual(
            body["samples"],
            {
                "count": 0,
                "first_recorded_at": None,
                "latest": None,
                "percentiles": None,
            },
        )
        reliability = body["reliability"]
        self.assertEqual(list(reliability), RELIABILITY_KEYS)
        self.assertEqual(
            (reliability["attempts"], reliability["successes"]), (0, 0)
        )
        # No attempts: the rate is unknown, not 0% or 100%.
        self.assertIsNone(reliability["success_rate"])
        self.assertIsNone(reliability["failure_rate"])
        self.assertEqual(set(reliability["failures_by_category"].values()), {0})

    def test_passes_analytics_results_through_without_recalculating(self):
        # A summary that does not match its observations: the serializer must
        # report the analytics result as given, not recompute it.
        observations = (
            analytics.Observation(NOW - datetime.timedelta(hours=1), 10.0),
        )
        summary = analytics.MetricSummary(
            count=7,
            first_at=NOW - datetime.timedelta(days=2),
            latest_at=NOW - datetime.timedelta(hours=1),
            latest_value=10.0,
            percentiles={50: 1.5, 95: 2.5, 99: 3.5},
        )
        reliability = {
            "attempts": 9,
            "successes": 3,
            "failures": 6,
            "success_rate": 0.123,
            "failure_rate": 0.877,
            "failures_by_category": {"timeout": 6},
        }
        result = analytics.MetricWindow(
            start=NOW - datetime.timedelta(days=7),
            end=NOW,
            observations=observations,
            summary=summary,
            reliability=reliability,
        )
        body = api.metrics_response(result, "7d", "ttft")
        self.assertEqual(body["samples"]["count"], 7)
        self.assertEqual(
            body["samples"]["percentiles"], {"p50": 1.5, "p95": 2.5, "p99": 3.5}
        )
        self.assertEqual(body["reliability"]["success_rate"], 0.123)
        self.assertEqual(
            body["reliability"]["failures_by_category"], {"timeout": 6}
        )

    def test_values_are_numbers_and_times_are_iso(self):
        observations = [
            analytics.Observation(NOW - datetime.timedelta(hours=h), v)
            for h, v in ((3, 120.0), (2, 80.0), (1, 100.0))
        ]
        reliability = {
            "attempts": 4,
            "successes": 3,
            "failures": 1,
            "success_rate": 0.75,
            "failure_rate": 0.25,
            "failures_by_category": {"timeout": 1},
        }
        body = api.metrics_response(
            self.window(observations, reliability), "24h", "ttft"
        )
        self.assertTrue(numbers_only(body["reliability"]))
        self.assertTrue(numbers_only(body["samples"]["percentiles"]))
        self.assertEqual(
            body["samples"]["latest"],
            {"recorded_at": "2026-11-30T11:00:00.000000Z", "value": 100.0},
        )
        for moment in timestamps(body):
            self.assertRegex(moment, ISO_UTC)

    def test_invalid_query_body_lists_valid_values_only(self):
        body = api.invalid_query_response()
        self.assertEqual(body["api_version"], "v1")
        error = body["error"]
        self.assertEqual(error["code"], "invalid_query")
        self.assertEqual(error["valid"]["metric"], list(query.METRICS))
        self.assertEqual(error["valid"]["window"], list(query.WINDOWS))
        self.assertEqual(
            error["defaults"],
            {"metric": query.DEFAULT_METRIC, "window": query.DEFAULT_WINDOW},
        )

    def test_api_depends_on_analytics_not_presentation_or_storage(self):
        tree = ast.parse(
            (REPO_ROOT / "llm_metrics" / "api.py").read_text(encoding="utf-8")
        )
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module == "llm_metrics"
            for alias in node.names
        }
        # No display formatting, no SQL, no statistics of its own.
        self.assertFalse(
            imported & {"dashboard", "web", "storage", "percentiles"}
        )
        self.assertIn("analytics", imported)


class MetricsEndpointTest(unittest.TestCase):
    """`GET /api/v1/metrics` through Flask, with the clock fixed at NOW."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db_path = pathlib.Path(tmp.name) / "data" / "llm_metrics.db"
        self.client = web.create_app(self.db_path).test_client()
        patches = [
            mock.patch.object(web, "_now", return_value=NOW),
            mock.patch("socket.socket.connect", side_effect=AssertionError),
            mock.patch("urllib.request.urlopen", side_effect=AssertionError),
        ]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def get_json(self, path, status=200):
        response = self.client.get(path)
        self.assertEqual(response.status_code, status)
        self.assertEqual(response.mimetype, "application/json")
        return json.loads(response.get_data(as_text=True))

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

    def save_attempt(self, attempt, hours_ago, env="test"):
        # Attempts are stamped with the real clock; move them to NOW's frame.
        request_id = storage.save_request(self.db_path, attempt, [], env)
        recorded_at = NOW - datetime.timedelta(hours=hours_ago)
        with contextlib.closing(storage.connect(self.db_path)) as conn:
            with conn:  # commits
                conn.execute(
                    "UPDATE requests SET recorded_at = ? WHERE id = ?",
                    (storage.format_timestamp(recorded_at), request_id),
                )

    def test_defaults_are_ttft_over_7d(self):
        body = self.get_json("/api/v1/metrics")
        self.assertEqual(body["metric"], {"name": "ttft", "unit": "ms"})
        self.assertEqual(body["window"]["name"], "7d")
        self.assertEqual(body["window"]["end"], "2026-11-30T12:00:00.000000Z")
        self.assertEqual(body["window"]["start"], "2026-11-23T12:00:00.000000Z")
        # Unrelated parameters are ignored, as on the HTML page.
        self.assertEqual(self.get_json("/api/v1/metrics?other=1"), body)

    def test_every_valid_metric_and_window(self):
        for window in query.WINDOWS:
            for metric, (_, unit) in query.METRICS.items():
                with self.subTest(window=window, metric=metric):
                    body = self.get_json(
                        f"/api/v1/metrics?window={window}&metric={metric}"
                    )
                    self.assertEqual(body["window"]["name"], window)
                    self.assertEqual(
                        body["metric"], {"name": metric, "unit": unit}
                    )
                    self.assertEqual(body["population"]["data"], "simulated")

    def test_invalid_queries_are_400_json_without_echo(self):
        hostile = "%3Cscript%3Ealert(1)%3C%2Fscript%3E"
        for query_string in (
            "metric=",
            "window=",
            "metric=TTFT",
            "window=1y",
            f"metric={hostile}",
            f"window={hostile}",
            "metric=ttft&metric=ttft",
            "window=24h&window=7d",
        ):
            with self.subTest(query=query_string):
                response = self.client.get(f"/api/v1/metrics?{query_string}")
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.mimetype, "application/json")
                text = response.get_data(as_text=True)
                body = json.loads(text)
                self.assertEqual(body["error"]["code"], "invalid_query")
                for echoed in ("script", "alert", "TTFT", "1y"):
                    self.assertNotIn(echoed, text)

    def test_metric_and_window_rules_match_the_html_dashboard(self):
        for query_string in ("", "metric=ttft&window=30d", "metric=bad"):
            with self.subTest(query=query_string):
                page = self.client.get(f"/?{query_string}").status_code
                endpoint = self.client.get(f"/api/v1/metrics?{query_string}")
                self.assertEqual(endpoint.status_code, page)

    def test_percentiles_and_reliability_use_analytics_populations(self):
        for hours_ago, value in ((5, 300.0), (4, 100.0), (3, 200.0)):
            self.save_observation(hours_ago, value)
        self.save_observation(2, 999.0, env="prod")  # never mixed in
        self.save_observation(2, 5.0, metric="total_latency")  # other metric
        for hours_ago in (5, 4, 3):
            self.save_attempt(ATTEMPT, hours_ago)
        self.save_attempt(FAILED_ATTEMPT, 1)
        self.save_attempt(FAILED_ATTEMPT, 1, env="prod")  # never counted

        body = self.get_json("/api/v1/metrics?window=24h")
        samples = body["samples"]
        # Successful observations only: 3 samples, no zero for the failure.
        self.assertEqual(samples["count"], 3)
        # Nearest rank over [100, 200, 300].
        self.assertEqual(
            samples["percentiles"], {"p50": 200.0, "p95": 300.0, "p99": 300.0}
        )
        start, end = query.window_bounds("24h", NOW)
        expected = analytics.load_metric_window(
            self.db_path,
            "test",
            "dummy",
            "dummy-model-v1",
            "ttft",
            start=start,
            end=end,
        )
        self.assertEqual(
            samples["percentiles"],
            {f"p{p}": v for p, v in expected.summary.percentiles.items()},
        )
        self.assertEqual(
            samples["latest"],
            {"recorded_at": "2026-11-30T09:00:00.000000Z", "value": 200.0},
        )
        self.assertEqual(
            samples["first_recorded_at"], "2026-11-30T07:00:00.000000Z"
        )
        # Reliability counts every attempt of the population, failed or not.
        reliability = body["reliability"]
        self.assertEqual(
            (
                reliability["attempts"],
                reliability["successes"],
                reliability["failures"],
            ),
            (4, 3, 1),
        )
        self.assertEqual(reliability["success_rate"], 0.75)
        self.assertEqual(reliability["failure_rate"], 0.25)
        self.assertEqual(reliability["failures_by_category"]["rate_limited"], 1)
        # JSON numbers, not display strings.
        self.assertTrue(numbers_only(reliability))
        self.assertTrue(numbers_only(samples["percentiles"]))
        for moment in timestamps(body):
            self.assertRegex(moment, ISO_UTC)

    def test_valid_empty_window_is_a_truthful_200(self):
        self.save_observation(48, 100.0)  # outside 24h
        body = self.get_json("/api/v1/metrics?window=24h")
        self.assertEqual(body["samples"]["count"], 0)
        self.assertIsNone(body["samples"]["latest"])
        self.assertIsNone(body["samples"]["percentiles"])
        self.assertEqual(body["reliability"]["attempts"], 0)
        self.assertIsNone(body["reliability"]["success_rate"])
        text = json.dumps(body)
        for marker in ('"—"', '"unknown"', "%", " ms"):
            self.assertNotIn(marker, text)

    def test_failures_only_window_has_rate_but_no_samples(self):
        self.save_attempt(FAILED_ATTEMPT, 1)
        body = self.get_json("/api/v1/metrics?window=24h")
        self.assertEqual(body["samples"]["count"], 0)
        self.assertIsNone(body["samples"]["percentiles"])
        self.assertEqual(body["reliability"]["attempts"], 1)
        self.assertEqual(body["reliability"]["success_rate"], 0.0)

    def test_unknown_api_paths_and_methods_are_json_errors(self):
        for path in ("/api/v1/requests", "/api/v2/metrics", "/api/"):
            with self.subTest(path=path):
                body = self.get_json(path, status=404)
                self.assertEqual(body["error"]["code"], "not_found")
        response = self.client.post("/api/v1/metrics")
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.mimetype, "application/json")
        self.assertIn("GET", response.headers["Allow"])
        self.assertEqual(
            json.loads(response.get_data(as_text=True))["error"]["code"],
            "method_not_allowed",
        )
        # The HTML pages keep their HTML errors.
        self.assertEqual(self.client.get("/missing").mimetype, "text/html")

    def test_server_errors_are_json_without_details(self):
        with mock.patch.object(
            api,
            "load_metrics_response",
            side_effect=RuntimeError("secret-xyz"),
        ), self.assertLogs(level="ERROR"):
            response = self.client.get("/api/v1/metrics")
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.mimetype, "application/json")
        text = response.get_data(as_text=True)
        self.assertEqual(
            json.loads(text)["error"]["code"], "internal_server_error"
        )
        for leaked in ("secret-xyz", "Traceback", "RuntimeError"):
            self.assertNotIn(leaked, text)

    def test_no_private_data_in_responses(self):
        self.save_observation(1, 100.0)
        self.save_attempt(ATTEMPT, 1)
        self.save_attempt(FAILED_ATTEMPT, 1)
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-secret"}):
            texts = [
                self.client.get(path).get_data(as_text=True)
                for path in (
                    "/api/v1/metrics",
                    "/api/v1/metrics?window=bad",
                    "/api/v1/missing",
                )
            ]
        for text in texts:
            for private in (
                "sk-test-secret",
                "prompt",
                "response_text",
                "diagnostics",
                "provider_request_id",
                "workload",
                "origin",
            ):
                self.assertNotIn(private, text)

    def test_responses_keep_the_security_header(self):
        for path in ("/api/v1/metrics", "/api/v1/metrics?metric=x", "/api/x"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(
                    response.headers["Content-Security-Policy"],
                    web.CONTENT_SECURITY_POLICY,
                )

    def test_serialization_is_deterministic(self):
        self.save_observation(1, 100.0)
        first = self.client.get("/api/v1/metrics").get_data()
        self.assertEqual(self.client.get("/api/v1/metrics").get_data(), first)
        self.assertEqual(list(json.loads(first)), TOP_LEVEL_KEYS)


if __name__ == "__main__":
    unittest.main()
