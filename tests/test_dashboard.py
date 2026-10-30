"""Tests for the dashboard pages: query validation, data loading, rendering.

Covers the aggregate page (windows, metrics, success rate, percentiles,
chart), the individual requests page, Benchmark API Spend, invalid queries,
HTML escaping, and the separation of simulated and real data. Each test uses
its own temporary database. The HTTP boundary is tested in test_web.py.
"""

import contextlib
import datetime
import pathlib
import re
import sqlite3
import tempfile
import time
import unittest
import urllib.parse

from llm_metrics import dashboard
from llm_metrics import storage
from llm_metrics import web

DUMMY_IDENTITY = {"provider": "dummy", "model": "dummy-model-v1"}
DUMMY = {**DUMMY_IDENTITY, "metric": "ttft"}
# A fixed "current time" so no test depends on the machine clock.
NOW = datetime.datetime(2026, 11, 30, 12, 0, tzinfo=datetime.timezone.utc)


def params(query):
    """Parses a query string the way the web layer does: repeated and blank
    values are kept, so validation can reject them."""
    return urllib.parse.parse_qs(query, keep_blank_values=True)


def visible_text(page):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", page))


def link(window, metric):
    return f'href="/?window={window}&amp;metric={metric}"'


def current(window, metric):
    return link(window, metric) + ' aria-current="page"'


def chart_point_count(page):
    match = re.search(r'<polyline[^>]*points="([^"]*)"', page)
    return len(match.group(1).split()) if match else 0


class DashboardTestCase(unittest.TestCase):
    """Gives each test its own temporary database and an app that reads it.

    Pages are rendered with the real templates. Views come from `dashboard`
    with an explicit "now", so no test depends on the machine clock; the HTTP
    routes themselves are tested in test_web.py.
    """

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db_path = pathlib.Path(tmp.name) / "observations.db"
        self.app = web.create_app(self.db_path)

    def render(self, template, view):
        """Renders a page template with a view, as the routes do."""
        with self.app.test_request_context():
            return web.render_page(template, view).get_data(as_text=True)

    def aggregate_page(self, window, metric, now=NOW):
        return self.render(
            "aggregate.html",
            dashboard.load_aggregate_view(self.db_path, window, metric, now),
        )

    def requests_page(self, data="simulated"):
        return self.render(
            "requests.html", dashboard.load_requests_view(self.db_path, data)
        )

    def save(self, recorded_at, value, environment="test", **overrides):
        result = {**DUMMY, "value": value, **overrides}
        storage.save_new_observations(
            self.db_path, [(recorded_at, result)], environment
        )

    def load(self, start, end):
        return storage.load_observations(
            self.db_path,
            "test",
            "dummy",
            "dummy-model-v1",
            "ttft",
            start=start,
            end=end,
        )


class LoadObservationsTest(DashboardTestCase):

    def test_filters_by_identity_and_orders_by_time(self):
        self.save(NOW - datetime.timedelta(hours=1), 105.0)
        self.save(NOW - datetime.timedelta(hours=5), 101.0)
        self.save(NOW - datetime.timedelta(hours=3), 103.0)
        for overrides in (
            {"provider": "other"},
            {"model": "other"},
            {"metric": "other"},
        ):
            self.save(NOW - datetime.timedelta(hours=2), 999.0, **overrides)
        self.save(NOW - datetime.timedelta(hours=2), 999.0, environment="prod")
        rows = self.load(NOW - datetime.timedelta(days=1), NOW)
        self.assertEqual([v for _, v in rows], [101.0, 103.0, 105.0])

    def test_both_boundaries_are_inclusive(self):
        start, end = NOW - datetime.timedelta(hours=24), NOW
        micro = datetime.timedelta(microseconds=1)
        self.save(start - micro, 1.0)  # just before the window
        self.save(start, 2.0)  # exactly at the cutoff: included
        self.save(start + datetime.timedelta(hours=12), 3.0)
        self.save(end, 4.0)  # exactly now: included
        self.save(end + micro, 5.0)  # in the future: excluded
        self.assertEqual([v for _, v in self.load(start, end)], [2.0, 3.0, 4.0])


class WindowTest(DashboardTestCase):

    def test_parse_query_defaults_and_values(self):
        self.assertEqual(dashboard.DEFAULT_WINDOW, "7d")
        self.assertEqual(dashboard.DEFAULT_METRIC, "ttft")
        self.assertEqual(dashboard.parse_query(params("")), ("7d", "ttft"))
        self.assertEqual(
            dashboard.parse_query(params("other=1")), ("7d", "ttft")
        )
        for name in ("24h", "7d", "30d"):
            self.assertEqual(
                dashboard.parse_query(params(f"window={name}")), (name, "ttft")
            )
        self.assertEqual(
            dashboard.parse_query(params("metric=total_latency")),
            ("7d", "total_latency"),
        )
        self.assertEqual(
            dashboard.parse_query(params("metric=ttft&window=30d")),
            ("30d", "ttft"),
        )

    def test_invalid_window_rejected(self):
        for query in (
            "window=",
            "window=1h",
            "window=7D",
            "window=365d",
            "window=24h&window=7d",
            "window=%3Cscript%3E",
        ):
            with self.subTest(query=query):
                with self.assertRaises(ValueError):
                    dashboard.parse_query(params(query))

    def test_invalid_metric_rejected(self):
        for query in (
            "metric=",
            "metric=TTFT",
            "metric=total",
            "metric=throughput",
            "metric=ttft&metric=total_latency",
            "metric=ttft&metric=ttft",
            "metric=%3Cscript%3E",
            "window=7d&metric=bogus",
            "metric=output_chunks_per_s&metric=ttft",
        ):
            with self.subTest(query=query):
                with self.assertRaises(ValueError):
                    dashboard.parse_query(params(query))

    def test_window_bounds_are_relative_to_now(self):
        self.assertEqual(
            dashboard.window_bounds("24h", NOW),
            (NOW - datetime.timedelta(hours=24), NOW),
        )
        self.assertEqual(
            dashboard.window_bounds("7d", NOW),
            (NOW - datetime.timedelta(days=7), NOW),
        )
        self.assertEqual(
            dashboard.window_bounds("30d", NOW),
            (NOW - datetime.timedelta(days=30), NOW),
        )


class BuildPageTest(DashboardTestCase):

    def setUp(self):
        super().setUp()
        # 24h holds 2 rows; 7d adds 2 more; 30d adds 2 more; one row is older
        # than 30d.
        for age, value in [
            (datetime.timedelta(hours=1), 100.0),
            (datetime.timedelta(hours=10), 110.0),
            (datetime.timedelta(days=2), 300.0),
            (datetime.timedelta(days=5), 310.0),
            (datetime.timedelta(days=10), 500.0),
            (datetime.timedelta(days=20), 510.0),
            (datetime.timedelta(days=40), 9999.0),
        ]:
            self.save(NOW - age, value)

    def test_windows_select_different_populations(self):
        expected = {
            # window: (count, p50, p95, p99) by nearest rank over that window
            # only
            "24h": (2, "100.0", "110.0", "110.0"),
            "7d": (4, "110.0", "310.0", "310.0"),
            "30d": (6, "300.0", "510.0", "510.0"),
        }
        for window, (count, p50, p95, p99) in expected.items():
            with self.subTest(window=window):
                page = self.aggregate_page(window, "ttft", NOW)
                text = visible_text(page)
                self.assertIn(f"{count} observations in window", text)
                self.assertIn(f"n = {count}", text)
                self.assertEqual(chart_point_count(page), count)
                self.assertIn(f"p50 {p50} ms", text)
                self.assertIn(f"p95 {p95} ms", text)
                self.assertIn(f"p99 {p99} ms", text)
                self.assertIn(
                    "100.0 ms", text
                )  # latest value is in every window
                self.assertNotIn("9999", text)  # older than 30d: never shown

    def test_selected_window_is_marked(self):
        page = self.aggregate_page("24h", "ttft", NOW)
        self.assertIn(current("24h", "ttft"), page)
        self.assertNotIn(current("7d", "ttft"), page)
        # Metric links keep the selected window; window links keep the metric.
        self.assertIn(link("24h", "total_latency"), page)
        self.assertIn(link("30d", "ttft"), page)

    def test_label_still_present(self):
        self.assertIn(
            "TEST / SIMULATED DATA",
            self.aggregate_page("7d", "ttft", NOW),
        )


class MetricSelectionTest(DashboardTestCase):

    def setUp(self):
        super().setUp()
        # One request at each age stores both metrics, as the CLI does.
        for age, ttft, total in [
            (datetime.timedelta(hours=1), 100.0, 180.0),
            (datetime.timedelta(hours=5), 110.0, 200.0),
            (datetime.timedelta(days=3), 300.0, 400.0),  # outside 24h
        ]:
            recorded_at = NOW - age
            self.save(recorded_at, ttft, metric="ttft")
            self.save(recorded_at, total, metric="total_latency")
        self.save(
            NOW - datetime.timedelta(hours=2), 999.0, metric="ttft"
        )  # extra TTFT-only row

    def test_each_metric_uses_only_its_own_population(self):
        expected = {
            # (window, metric): (count, p50, p95, latest)
            ("24h", "ttft"): (
                3,
                "110.0",
                "999.0",
                "100.0",
            ),  # sorted 100, 110, 999
            ("24h", "total_latency"): (2, "180.0", "200.0", "180.0"),
            ("7d", "ttft"): (4, "110.0", "999.0", "100.0"),
            ("7d", "total_latency"): (3, "200.0", "400.0", "180.0"),
        }
        for (window, metric), (count, p50, p95, latest) in expected.items():
            with self.subTest(window=window, metric=metric):
                page = self.aggregate_page(window, metric, NOW)
                text = visible_text(page)
                self.assertIn(f"{count} observations in window", text)
                self.assertIn(f"n = {count}", text)
                self.assertEqual(chart_point_count(page), count)
                self.assertIn(f"p50 {p50} ms", text)
                self.assertIn(f"p95 {p95} ms", text)
                self.assertIn(f"{latest} ms", text)
                self.assertIn(current(window, metric), page)
                if metric == "total_latency":
                    self.assertNotIn(
                        "999.0", text
                    )  # a TTFT-only value never leaks in
                    self.assertIn("Total latency p50", text)
                else:
                    self.assertIn("TTFT p50", text)

    def test_throughput_label_unit_and_population(self):
        for age, rate in [
            (datetime.timedelta(hours=1), 50.0),
            (datetime.timedelta(hours=3), 40.0),
            (datetime.timedelta(days=3), 30.0),
            (datetime.timedelta(days=40), 999.0),
        ]:
            self.save(NOW - age, rate, metric="output_chunks_per_s")
        expected = {
            "24h": (2, "40.0", "50.0"),
            "7d": (3, "40.0", "50.0"),
            "30d": (3, "40.0", "50.0"),
        }
        for window, (count, p50, p99) in expected.items():
            with self.subTest(window=window):
                page = self.aggregate_page(window, "output_chunks_per_s", NOW)
                text = visible_text(page)
                self.assertIn("Output chunk throughput p50", text)
                self.assertIn(f"p50 {p50} chunks/s", text)
                self.assertIn(f"p99 {p99} chunks/s", text)
                self.assertIn("50.0 chunks/s", text)  # latest
                self.assertIn(f"n = {count}", text)
                self.assertEqual(chart_point_count(page), count)
                self.assertIn(
                    'fill="#555">chunks/s</text>', page
                )  # y-axis unit label
                self.assertNotRegex(
                    text, r"\d ms\b"
                )  # never labelled as milliseconds
                self.assertNotIn("999.0", text)  # older than 30d
                self.assertIn(current(window, "output_chunks_per_s"), page)
        # The latency metrics' populations are untouched by throughput rows.
        ttft_text = visible_text(self.aggregate_page("24h", "ttft", NOW))
        self.assertIn("n = 3", ttft_text)
        self.assertNotIn("chunks/s", ttft_text.split("Window 24h")[1])

    def test_empty_metric_in_window_renders_cleanly(self):
        page = self.aggregate_page(
            "24h", "total_latency", NOW + datetime.timedelta(days=10)
        )
        text = visible_text(page)
        self.assertIn(
            "No Total latency observations in the selected window (24h)", text
        )
        self.assertNotIn("<svg", page)
        self.assertIn("TEST / SIMULATED DATA", text)


class ReliabilityTest(DashboardTestCase):

    def reliability_text(self, counts):
        """Returns the reliability section's text, cells separated by spaces."""
        start, end = dashboard.window_bounds("7d", NOW)
        page = self.render(
            "aggregate.html",
            dashboard.aggregate_view([], "7d", "ttft", start, end, counts),
        )
        section = page[
            page.index('<section class="reliability">') : page.index(
                "</section>"
            )
        ]
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", section))

    def test_success_rate_and_failures_by_category(self):
        text = self.reliability_text(
            {"success": 7, "rate_limited": 2, "timeout": 1}
        )
        self.assertIn("Observed benchmark success rate (7d)", text)
        self.assertIn("70.0%", text)
        self.assertIn("7 of 10 attempts succeeded (3 failed, 30.0%)", text)
        self.assertIn("Rate limited 2", text)
        self.assertIn("Timeout 1", text)
        self.assertIn("Provider/server error 0", text)
        self.assertIn("Network/transport error 0", text)
        self.assertIn("Invalid response 0", text)
        self.assertIn("not the provider's overall uptime", text)

    def test_no_attempts_shows_no_rate(self):
        text = self.reliability_text({})
        self.assertIn("No benchmark attempts in the selected window (7d)", text)
        self.assertNotIn("%", text)

    def test_all_failed_is_zero_percent_not_no_rate(self):
        self.assertIn("0.0%", self.reliability_text({"provider_error": 3}))

    def test_failures_count_for_rate_but_not_for_percentiles(self):
        now = datetime.datetime.now(
            datetime.timezone.utc
        )  # save_request stamps the real time
        storage.save_request(
            self.db_path,
            REQUEST,
            metric_results(total_latency=180.0, ttft=100.0),
            "test",
        )
        for category in ("timeout", "invalid_response"):
            storage.save_request(
                self.db_path,
                {
                    **REQUEST,
                    "outcome": category,
                    "input_tokens": None,
                    "output_tokens": None,
                    "input_cost": None,
                    "output_cost": None,
                    "total_cost": None,
                    "failed_after_ms": 5.0,
                },
                [],
                "test",
            )
        text = visible_text(
            self.aggregate_page(
                "24h", "total_latency", now + datetime.timedelta(seconds=5)
            )
        )
        self.assertIn("1 of 3 attempts succeeded (2 failed, 66.7%)", text)
        self.assertIn("33.3%", text)
        self.assertIn("Total latency (successful attempts only)", text)
        self.assertIn("n = 1", text)  # failed attempts add no latency values
        self.assertIn("p50 180.0 ms", text)


class EmptyAndRenderTest(DashboardTestCase):

    def test_empty_valid_window_renders_cleanly(self):
        self.save(NOW - datetime.timedelta(days=3), 120.0)  # outside 24h
        page = self.aggregate_page("24h", "ttft", NOW)
        text = visible_text(page)
        self.assertIn("No TTFT observations in the selected window (24h)", text)
        self.assertIn("TEST / SIMULATED DATA", text)
        self.assertNotIn("<svg", page)
        self.assertNotIn("p50", text)
        self.assertTrue(page.rstrip().endswith("</html>"))

    def test_empty_database_renders_cleanly(self):
        page = self.aggregate_page("7d", "ttft", NOW)
        self.assertIn("observations in the selected window", page)

    def test_single_observation(self):
        start, end = dashboard.window_bounds("24h", NOW)
        page = self.render(
            "aggregate.html",
            dashboard.aggregate_view(
                [("2026-11-30T11:00:00.000000Z", 101.0)],
                "24h",
                "ttft",
                start,
                end,
                {},
            ),
        )
        text = visible_text(page)
        for p in ("p50", "p95", "p99"):
            self.assertIn(f"{p} 101.0 ms", text)
        self.assertIn("1 observation in window", text)
        self.assertEqual(chart_point_count(page), 1)


REQUEST = {
    **DUMMY_IDENTITY,
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


def metric_results(**values):
    return [
        {**DUMMY_IDENTITY, "metric": m, "value": v} for m, v in values.items()
    ]


class RequestsViewTest(DashboardTestCase):

    def test_empty_state(self):
        page = self.requests_page("simulated")
        text = visible_text(page)
        self.assertIn("TEST / SIMULATED DATA", text)
        self.assertIn("No benchmark attempts yet", text)
        self.assertNotIn("<table", page)

    def test_shows_request_facts_metrics_and_cost(self):
        first = storage.save_request(
            self.db_path,
            {**REQUEST, "output_tokens": 2},
            metric_results(total_latency=150.0, ttft=95.0),
            "test",
        )
        time.sleep(0.002)
        second = storage.save_request(
            self.db_path,
            REQUEST,
            metric_results(
                total_latency=181.4,
                ttft=100.3,
                output_tokens_per_s=87.5,
                output_chunks_per_s=49.4,
            ),
            "test",
        )
        page = self.requests_page("simulated")
        text = visible_text(page)
        self.assertIn("TEST / SIMULATED DATA", text)
        self.assertIn("simulated tokenizer", text)
        self.assertIn("simulated prices", text)
        for header in (
            "Input tokens",
            "Max output tokens",
            "Output tokens",
            "Total latency (ms)",
            "TTFT (ms)",
            "Throughput (tokens/s)",
            "Throughput (chunks/s)",
            "Input cost ($)",
            "Output cost ($)",
            "Total cost ($)",
            "Workload",
            "Origin",
        ):
            self.assertIn(header, text)
        # Newest request first, identified by its id prefix.
        self.assertLess(page.index(second[:8]), page.index(first[:8]))
        newest_row = page[
            page.index(second[:8]) : page.index(first[:8])
        ]  # from its id cell on
        cells = re.findall(r"<td[^>]*>(.*?)</td>", newest_row)
        # outcome, total latency, TTFT, tokens/s, chunks/s, input/output/max
        # tokens, total/input/output cost, failed after, provider/model,
        # workload, origin
        self.assertEqual(
            cells[:15],
            [
                "success",
                "181.4",
                "100.3",
                "87.5",
                "49.4",
                "3",
                "7",
                "64",
                "0.000062",
                "0.000006",
                "0.000056",
                "—",
                "dummy / dummy-model-v1",
                "simulated.default.v1",
                "local / unknown",
            ],
        )
        # Token throughput is shown before (preferred over) chunk throughput.
        self.assertLess(
            text.index("Throughput (tokens/s)"),
            text.index("Throughput (chunks/s)"),
        )
        # The older request had no throughput: shown as missing, not invented.
        older_row = page[page.index(first[:8]) :]
        self.assertIn("<td>—</td>", older_row)
        # Total latency precedes TTFT: it is the primary latency.
        self.assertLess(
            text.index("Total latency (ms)"), text.index("TTFT (ms)")
        )

    def test_failed_attempt_row_shows_category_and_unknowns(self):
        failed = {
            **REQUEST,
            "outcome": "transport_error",
            "input_tokens": None,
            "output_tokens": None,
            "input_cost": None,
            "output_cost": None,
            "total_cost": None,
            "failed_after_ms": 42.0,
        }
        request_id = storage.save_request(self.db_path, failed, [], "test")
        page = self.requests_page("simulated")
        row = page[page.index(request_id[:8]) :]
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row)
        self.assertEqual(
            visible_text(cells[0]), "FAILED: Network/transport error"
        )
        # latency, TTFT, both throughputs, input/output tokens unknown; max is
        # known
        self.assertEqual(cells[1:8], ["—", "—", "—", "—", "—", "—", "64"])
        self.assertEqual(
            cells[8:12], ["—", "—", "—", "42.0"]
        )  # costs unknown; failed after
        # Workload and origin are known for a failed attempt too.
        self.assertEqual(
            cells[13:15], ["simulated.default.v1", "local / unknown"]
        )
        self.assertNotIn(">0<", row)  # nothing shown as zero

    def test_historical_rows_show_unknown_workload_and_origin(self):
        request_id = storage.save_request(
            self.db_path, REQUEST, metric_results(total_latency=1.0), "test"
        )
        # Make it look like a row recorded before these facts were tracked.
        with contextlib.closing(sqlite3.connect(self.db_path)) as conn:
            with conn:  # Commits, or rolls back on error.
                conn.execute(
                    "UPDATE requests SET workload_id = NULL, origin_cloud ="
                    " NULL,"
                    " origin_region = NULL, cache_policy = 'unknown' WHERE id"
                    " = ?",
                    (request_id,),
                )
        page = self.requests_page("simulated")
        cells = re.findall(
            r"<td[^>]*>(.*?)</td>", page[page.index(request_id[:8]) :]
        )
        # workload, origin, cache policy, cached input tokens: unknown, not
        # invented
        self.assertEqual(cells[-4:], ["—", "—", "unknown", "—"])

    def test_cache_facts_are_shown_and_zero_is_not_unknown(self):
        cases = (
            ("disabled", 0, ["disabled", "0"]),
            ("disabled", 1024, ["disabled", "1024"]),
            ("provider_default", None, ["provider_default", "—"]),
        )
        for policy, cached, expected in cases:
            with self.subTest(policy=policy, cached=cached):
                request_id = storage.save_request(
                    self.db_path,
                    {
                        **REQUEST,
                        "cache_policy": policy,
                        "cached_input_tokens": cached,
                    },
                    metric_results(total_latency=1.0),
                    "test",
                )
                page = self.requests_page("simulated")
                row = page[page.index(request_id[:8]) :]
                cells = re.findall(
                    r"<td[^>]*>(.*?)</td>", row[: row.index("</tr>")]
                )
                self.assertEqual(cells[-2:], expected)
        text = visible_text(page)
        self.assertIn("Cache policy", text)
        self.assertIn("Cached input tokens", text)
        self.assertIn("not reported, which is not zero", text)

    def test_real_view_shows_token_throughput_workload_and_origin(self):
        real = {
            **REQUEST,
            "provider": "openai",
            "model": "gpt-6-luna",
            "workload_id": "smoke.short_text.v2",
            "origin_cloud": "aws",
            "origin_region": "us-east-1",
        }
        storage.save_request(
            self.db_path,
            real,
            [
                {
                    "provider": "openai",
                    "model": "gpt-6-luna",
                    "metric": m,
                    "value": v,
                }
                for m, v in (
                    ("total_latency", 3880.7),
                    ("ttft", 3630.3),
                    ("output_tokens_per_s", 56.0),
                    ("output_chunks_per_s", 36.4),
                )
            ],
            "prod",
        )
        text = visible_text(self.requests_page("real"))
        for value in ("56.0", "36.4", "smoke.short_text.v2", "aws / us-east-1"):
            self.assertIn(value, text)

    def test_text_from_storage_is_escaped(self):
        storage.save_request(
            self.db_path,
            {**REQUEST, "model": "<script>x</script>"},
            metric_results(total_latency=1.0),
            "test",
        )
        page = self.requests_page("simulated")
        self.assertNotIn("<script>x", page)
        self.assertIn("&lt;script&gt;x", page)

    def test_only_test_environment_requests_are_listed(self):
        storage.save_request(
            self.db_path, REQUEST, metric_results(total_latency=1.0), "prod"
        )
        page = self.requests_page("simulated")
        self.assertIn("No benchmark attempts yet", page)


def spend_row(
    provider="openai",
    model="gpt-6-luna",
    successful_calls=2,
    failed_attempts=0,
    input_tokens=60,
    output_tokens=45,
    total_cost=0.0000285,
):
    return {
        "provider": provider,
        "model": model,
        "attempts": successful_calls + failed_attempts,
        "successful_calls": successful_calls,
        "failed_attempts": failed_attempts,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_cost": total_cost,
    }


class SpendPageTest(DashboardTestCase):

    def spend_page(self, rows, window="30d"):
        start, end = dashboard.window_bounds(window, NOW)
        return self.render(
            "spend.html", dashboard.spend_view(rows, window, start, end)
        )

    def cells_text(self, page):
        table = page[page.index("<table") : page.index("</table>")]
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", table))

    def test_explains_what_spend_is_and_is_not(self):
        text = visible_text(self.spend_page([]))
        self.assertIn("REAL PROVIDER DATA", text)
        self.assertNotIn("TEST / SIMULATED DATA", text)
        self.assertIn(
            "the API token cost incurred by llm-metrics to run its own"
            " benchmark requests",
            text,
        )
        for excluded in (
            "not the provider's revenue",
            "not what every user pays",
            "not hosting or infrastructure cost",
            "not a workload-independent price comparison",
        ):
            self.assertIn(excluded, text)
        self.assertIn(
            "No real benchmark attempts in the selected window (30d)", text
        )

    def test_rows_per_provider_model_and_grand_total(self):
        page = self.spend_page(
            [
                spend_row(),
                spend_row(
                    model="other-model",
                    successful_calls=1,
                    failed_attempts=2,
                    input_tokens=10,
                    output_tokens=10,
                    total_cost=0.000006,
                ),
                spend_row(
                    model="flaky-model",
                    successful_calls=0,
                    failed_attempts=1,
                    input_tokens=None,
                    output_tokens=None,
                    total_cost=None,
                ),
            ]
        )
        text = self.cells_text(page)
        self.assertIn("openai gpt-6-luna 2 60 45 $0.000029 0", text)
        self.assertIn("openai other-model 1 10 10 $0.000006 2", text)
        # A failure-only group has unknown cost, never $0.
        self.assertIn("openai flaky-model 0 — — unknown 1", text)
        self.assertIn(
            "All providers 3 70 55 $0.000034 3", text
        )  # known costs only
        self.assertNotIn("$0.000000", text)

    def test_only_real_data_from_the_database(self):
        storage.save_request(
            self.db_path, REQUEST, metric_results(total_latency=1.0), "test"
        )  # simulated
        text = visible_text(
            self.render(
                "spend.html",
                dashboard.load_spend_view(
                    self.db_path,
                    "30d",
                    datetime.datetime.now(datetime.timezone.utc),
                ),
            )
        )
        self.assertIn("No real benchmark attempts", text)
        self.assertNotIn(
            "dummy-model-v1", text.split("Benchmark API Spend", 2)[-1]
        )


class RequestsDataSelectorTest(DashboardTestCase):

    def test_real_requests_are_labelled_real(self):
        real = {
            **REQUEST,
            "provider": "openai",
            "model": "gpt-6-luna",
            "input_price_per_1m": 0.1,
            "output_price_per_1m": 0.5,
        }
        storage.save_request(
            self.db_path, real, metric_results(total_latency=900.0), "prod"
        )
        page = self.requests_page("real")
        text = visible_text(page)
        self.assertIn("REAL PROVIDER DATA", text)
        self.assertNotIn("TEST / SIMULATED DATA", text)
        self.assertIn("reported by the provider", text)
        self.assertIn("openai / gpt-6-luna", text)
        self.assertIn('href="/requests?data=real" aria-current="page"', page)

    def test_simulated_requests_keep_the_simulated_label(self):
        page = self.render(
            "requests.html", dashboard.requests_view([], "simulated")
        )
        self.assertIn("TEST / SIMULATED DATA", page)
        self.assertNotIn("REAL PROVIDER DATA", page)


if __name__ == "__main__":
    unittest.main()
