import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from llm_metrics.dashboard import (
    DEFAULT_METRIC,
    DEFAULT_WINDOW,
    HOST,
    build_page,
    make_server,
    parse_query,
    render_page,
    render_requests_page,
    window_bounds,
)
from llm_metrics.storage import (
    load_observations,
    load_recent_requests,
    save_new_observations,
    save_request,
)

DUMMY_IDENTITY = {"provider": "dummy", "model": "dummy-model-v1"}
DUMMY = {**DUMMY_IDENTITY, "metric": "ttft"}
# A fixed "current time" so no test depends on the machine clock.
NOW = datetime(2026, 11, 30, 12, 0, tzinfo=timezone.utc)


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
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db_path = Path(tmp.name) / "observations.db"

    def save(self, recorded_at, value, environment="test", **overrides):
        result = {**DUMMY, "value": value, **overrides}
        save_new_observations(self.db_path, [(recorded_at, result)], environment)

    def load(self, start, end):
        return load_observations(
            self.db_path, "test", "dummy", "dummy-model-v1", "ttft", start=start, end=end
        )


class LoadObservationsTest(DashboardTestCase):
    def test_filters_by_identity_and_orders_by_time(self):
        self.save(NOW - timedelta(hours=1), 105.0)
        self.save(NOW - timedelta(hours=5), 101.0)
        self.save(NOW - timedelta(hours=3), 103.0)
        for overrides in ({"provider": "other"}, {"model": "other"}, {"metric": "other"}):
            self.save(NOW - timedelta(hours=2), 999.0, **overrides)
        self.save(NOW - timedelta(hours=2), 999.0, environment="prod")
        rows = self.load(NOW - timedelta(days=1), NOW)
        self.assertEqual([v for _, v in rows], [101.0, 103.0, 105.0])

    def test_both_boundaries_are_inclusive(self):
        start, end = NOW - timedelta(hours=24), NOW
        micro = timedelta(microseconds=1)
        self.save(start - micro, 1.0)  # just before the window
        self.save(start, 2.0)          # exactly at the cutoff: included
        self.save(start + timedelta(hours=12), 3.0)
        self.save(end, 4.0)            # exactly now: included
        self.save(end + micro, 5.0)    # in the future: excluded
        self.assertEqual([v for _, v in self.load(start, end)], [2.0, 3.0, 4.0])


class WindowTest(DashboardTestCase):
    def test_parse_query_defaults_and_values(self):
        self.assertEqual(DEFAULT_WINDOW, "7d")
        self.assertEqual(DEFAULT_METRIC, "ttft")
        self.assertEqual(parse_query(""), ("7d", "ttft"))
        self.assertEqual(parse_query("other=1"), ("7d", "ttft"))
        for name in ("24h", "7d", "30d"):
            self.assertEqual(parse_query(f"window={name}"), (name, "ttft"))
        self.assertEqual(parse_query("metric=total_latency"), ("7d", "total_latency"))
        self.assertEqual(parse_query("metric=ttft&window=30d"), ("30d", "ttft"))

    def test_invalid_window_rejected(self):
        for query in ("window=", "window=1h", "window=7D", "window=365d",
                      "window=24h&window=7d", "window=%3Cscript%3E"):
            with self.subTest(query=query):
                with self.assertRaises(ValueError):
                    parse_query(query)

    def test_invalid_metric_rejected(self):
        for query in ("metric=", "metric=TTFT", "metric=total", "metric=throughput",
                      "metric=ttft&metric=total_latency", "metric=ttft&metric=ttft",
                      "metric=%3Cscript%3E", "window=7d&metric=bogus",
                      "metric=output_chunks_per_s&metric=ttft"):
            with self.subTest(query=query):
                with self.assertRaises(ValueError):
                    parse_query(query)

    def test_window_bounds_are_relative_to_now(self):
        self.assertEqual(window_bounds("24h", NOW), (NOW - timedelta(hours=24), NOW))
        self.assertEqual(window_bounds("7d", NOW), (NOW - timedelta(days=7), NOW))
        self.assertEqual(window_bounds("30d", NOW), (NOW - timedelta(days=30), NOW))


class BuildPageTest(DashboardTestCase):
    def setUp(self):
        super().setUp()
        # 24h holds 2 rows; 7d adds 2 more; 30d adds 2 more; one row is older than 30d.
        for age, value in [
            (timedelta(hours=1), 100.0), (timedelta(hours=10), 110.0),
            (timedelta(days=2), 300.0), (timedelta(days=5), 310.0),
            (timedelta(days=10), 500.0), (timedelta(days=20), 510.0),
            (timedelta(days=40), 9999.0),
        ]:
            self.save(NOW - age, value)

    def test_windows_select_different_populations(self):
        expected = {
            # window: (count, p50, p95, p99) by nearest rank over that window only
            "24h": (2, "100.0", "110.0", "110.0"),
            "7d": (4, "110.0", "310.0", "310.0"),
            "30d": (6, "300.0", "510.0", "510.0"),
        }
        for window, (count, p50, p95, p99) in expected.items():
            with self.subTest(window=window):
                page = build_page(self.db_path, window, "ttft", NOW)
                text = visible_text(page)
                self.assertIn(f"{count} observations in window", text)
                self.assertIn(f"n = {count}", text)
                self.assertEqual(chart_point_count(page), count)
                self.assertIn(f"p50 {p50} ms", text)
                self.assertIn(f"p95 {p95} ms", text)
                self.assertIn(f"p99 {p99} ms", text)
                self.assertIn("100.0 ms", text)  # latest value is in every window
                self.assertNotIn("9999", text)    # older than 30d: never shown

    def test_selected_window_is_marked(self):
        page = build_page(self.db_path, "24h", "ttft", NOW)
        self.assertIn(current("24h", "ttft"), page)
        self.assertNotIn(current("7d", "ttft"), page)
        # Metric links keep the selected window; window links keep the metric.
        self.assertIn(link("24h", "total_latency"), page)
        self.assertIn(link("30d", "ttft"), page)

    def test_label_still_present(self):
        self.assertIn("TEST / SIMULATED DATA", build_page(self.db_path, "7d", "ttft", NOW))


class MetricSelectionTest(DashboardTestCase):
    def setUp(self):
        super().setUp()
        # One request at each age stores both metrics, as the CLI does.
        for age, ttft, total in [
            (timedelta(hours=1), 100.0, 180.0),
            (timedelta(hours=5), 110.0, 200.0),
            (timedelta(days=3), 300.0, 400.0),   # outside 24h
        ]:
            recorded_at = NOW - age
            self.save(recorded_at, ttft, metric="ttft")
            self.save(recorded_at, total, metric="total_latency")
        self.save(NOW - timedelta(hours=2), 999.0, metric="ttft")  # extra TTFT-only row

    def test_each_metric_uses_only_its_own_population(self):
        expected = {
            # (window, metric): (count, p50, p95, latest)
            ("24h", "ttft"): (3, "110.0", "999.0", "100.0"),  # sorted 100, 110, 999
            ("24h", "total_latency"): (2, "180.0", "200.0", "180.0"),
            ("7d", "ttft"): (4, "110.0", "999.0", "100.0"),
            ("7d", "total_latency"): (3, "200.0", "400.0", "180.0"),
        }
        for (window, metric), (count, p50, p95, latest) in expected.items():
            with self.subTest(window=window, metric=metric):
                page = build_page(self.db_path, window, metric, NOW)
                text = visible_text(page)
                self.assertIn(f"{count} observations in window", text)
                self.assertIn(f"n = {count}", text)
                self.assertEqual(chart_point_count(page), count)
                self.assertIn(f"p50 {p50} ms", text)
                self.assertIn(f"p95 {p95} ms", text)
                self.assertIn(f"{latest} ms", text)
                self.assertIn(current(window, metric), page)
                if metric == "total_latency":
                    self.assertNotIn("999.0", text)  # a TTFT-only value never leaks in
                    self.assertIn("Total latency p50", text)
                else:
                    self.assertIn("TTFT p50", text)

    def test_throughput_label_unit_and_population(self):
        for age, rate in [(timedelta(hours=1), 50.0), (timedelta(hours=3), 40.0),
                          (timedelta(days=3), 30.0), (timedelta(days=40), 999.0)]:
            self.save(NOW - age, rate, metric="output_chunks_per_s")
        expected = {"24h": (2, "40.0", "50.0"), "7d": (3, "40.0", "50.0"), "30d": (3, "40.0", "50.0")}
        for window, (count, p50, p99) in expected.items():
            with self.subTest(window=window):
                page = build_page(self.db_path, window, "output_chunks_per_s", NOW)
                text = visible_text(page)
                self.assertIn("Output throughput p50", text)
                self.assertIn(f"p50 {p50} chunks/s", text)
                self.assertIn(f"p99 {p99} chunks/s", text)
                self.assertIn("50.0 chunks/s", text)  # latest
                self.assertIn(f"n = {count}", text)
                self.assertEqual(chart_point_count(page), count)
                self.assertIn('fill="#555">chunks/s</text>', page)  # y-axis unit label
                self.assertNotRegex(text, r"\d ms\b")  # never labelled as milliseconds
                self.assertNotIn("999", text)  # older than 30d
                self.assertIn(current(window, "output_chunks_per_s"), page)
        # The latency metrics' populations are untouched by throughput rows.
        ttft_text = visible_text(build_page(self.db_path, "24h", "ttft", NOW))
        self.assertIn("n = 3", ttft_text)
        self.assertNotIn("chunks/s", ttft_text.split("Window 24h")[1])

    def test_empty_metric_in_window_renders_cleanly(self):
        page = build_page(self.db_path, "24h", "total_latency", NOW + timedelta(days=10))
        text = visible_text(page)
        self.assertIn("No Total latency observations in the selected window (24h)", text)
        self.assertNotIn("<svg", page)
        self.assertIn("TEST / SIMULATED DATA", text)


class ReliabilityTest(DashboardTestCase):
    def render(self, counts):
        """Text of the reliability section only, with cells separated by spaces."""
        start, end = window_bounds("7d", NOW)
        page = render_page([], "7d", "ttft", start, end, counts)
        section = page[page.index('<section class="reliability">'):page.index("</section>")]
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", section))

    def test_success_rate_and_failures_by_category(self):
        text = self.render({"success": 7, "rate_limited": 2, "timeout": 1})
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
        text = self.render({})
        self.assertIn("No benchmark attempts in the selected window (7d)", text)
        self.assertNotIn("%", text)

    def test_all_failed_is_zero_percent_not_no_rate(self):
        self.assertIn("0.0%", self.render({"provider_error": 3}))

    def test_failures_count_for_rate_but_not_for_percentiles(self):
        now = datetime.now(timezone.utc)  # save_request stamps the real time
        save_request(self.db_path, REQUEST, metric_results(total_latency=180.0, ttft=100.0), "test")
        for category in ("timeout", "invalid_response"):
            save_request(self.db_path, {**REQUEST, "outcome": category, "input_tokens": None,
                                        "output_tokens": None, "input_cost": None, "output_cost": None,
                                        "total_cost": None, "failed_after_ms": 5.0}, [], "test")
        text = visible_text(build_page(self.db_path, "24h", "total_latency", now + timedelta(seconds=5)))
        self.assertIn("1 of 3 attempts succeeded (2 failed, 66.7%)", text)
        self.assertIn("33.3%", text)
        self.assertIn("Total latency (successful attempts only)", text)
        self.assertIn("n = 1", text)  # failed attempts add no latency values
        self.assertIn("p50 180.0 ms", text)


class EmptyAndRenderTest(DashboardTestCase):
    def test_empty_valid_window_renders_cleanly(self):
        self.save(NOW - timedelta(days=3), 120.0)  # outside 24h
        page = build_page(self.db_path, "24h", "ttft", NOW)
        text = visible_text(page)
        self.assertIn("No TTFT observations in the selected window (24h)", text)
        self.assertIn("TEST / SIMULATED DATA", text)
        self.assertNotIn("<svg", page)
        self.assertNotIn("p50", text)
        self.assertTrue(page.rstrip().endswith("</html>"))

    def test_empty_database_renders_cleanly(self):
        page = build_page(self.db_path, "7d", "ttft", NOW)
        self.assertIn("observations in the selected window", page)

    def test_single_observation(self):
        start, end = window_bounds("24h", NOW)
        page = render_page([("2026-11-30T11:00:00.000000Z", 101.0)], "24h", "ttft", start, end, {})
        text = visible_text(page)
        for p in ("p50", "p95", "p99"):
            self.assertIn(f"{p} 101.0 ms", text)
        self.assertIn("1 observation in window", text)
        self.assertEqual(chart_point_count(page), 1)


REQUEST = {
    **DUMMY_IDENTITY,
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
    return [{**DUMMY_IDENTITY, "metric": m, "value": v} for m, v in values.items()]


class RequestsViewTest(DashboardTestCase):
    def test_empty_state(self):
        page = render_requests_page(load_recent_requests(self.db_path, "test", 20))
        text = visible_text(page)
        self.assertIn("TEST / SIMULATED DATA", text)
        self.assertIn("No benchmark attempts yet", text)
        self.assertNotIn("<table", page)

    def test_shows_request_facts_metrics_and_cost(self):
        first = save_request(self.db_path, {**REQUEST, "output_tokens": 2},
                             metric_results(total_latency=150.0, ttft=95.0), "test")
        time.sleep(0.002)
        second = save_request(self.db_path, REQUEST,
                              metric_results(total_latency=181.4, ttft=100.3, output_chunks_per_s=49.4),
                              "test")
        page = render_requests_page(load_recent_requests(self.db_path, "test", 20))
        text = visible_text(page)
        self.assertIn("TEST / SIMULATED DATA", text)
        self.assertIn("simulated tokenizer", text)
        self.assertIn("simulated prices", text)
        for header in ("Input tokens", "Max output tokens", "Output tokens", "Total latency (ms)",
                       "TTFT (ms)", "Throughput (chunks/s)", "Input cost ($)", "Output cost ($)",
                       "Total cost ($)"):
            self.assertIn(header, text)
        # Newest request first, identified by its id prefix.
        self.assertLess(page.index(second[:8]), page.index(first[:8]))
        newest_row = page[page.index(second[:8]):page.index(first[:8])]  # from its id cell on
        cells = re.findall(r"<td[^>]*>(.*?)</td>", newest_row)
        # total latency, TTFT, throughput, input/output/max tokens, total/input/output cost
        # outcome, total latency, TTFT, throughput, input/output/max tokens,
        # total/input/output cost, failed after
        self.assertEqual(cells[:11], ["success", "181.4", "100.3", "49.4", "3", "7", "64",
                                      "0.000062", "0.000006", "0.000056", "—"])
        # The older request had no throughput: shown as missing, not invented.
        older_row = page[page.index(first[:8]):]
        self.assertIn("<td>—</td>", older_row)
        # Total latency precedes TTFT: it is the primary latency.
        self.assertLess(text.index("Total latency (ms)"), text.index("TTFT (ms)"))

    def test_failed_attempt_row_shows_category_and_unknowns(self):
        failed = {**REQUEST, "outcome": "transport_error", "input_tokens": None,
                  "output_tokens": None, "input_cost": None, "output_cost": None,
                  "total_cost": None, "failed_after_ms": 42.0}
        request_id = save_request(self.db_path, failed, [], "test")
        page = render_requests_page(load_recent_requests(self.db_path, "test", 20))
        row = page[page.index(request_id[:8]):]
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row)
        self.assertEqual(visible_text(cells[0]), "FAILED: Network/transport error")
        # latency, TTFT, throughput, input/output tokens unknown; max is known
        self.assertEqual(cells[1:7], ["—", "—", "—", "—", "—", "64"])
        self.assertEqual(cells[7:11], ["—", "—", "—", "42.0"])  # costs unknown; failed after
        self.assertNotIn(">0<", row)  # nothing shown as zero

    def test_text_from_storage_is_escaped(self):
        save_request(self.db_path, {**REQUEST, "model": "<script>x</script>"},
                     metric_results(total_latency=1.0), "test")
        page = render_requests_page(load_recent_requests(self.db_path, "test", 20))
        self.assertNotIn("<script>x", page)
        self.assertIn("&lt;script&gt;x", page)

    def test_only_test_environment_requests_are_listed(self):
        save_request(self.db_path, REQUEST, metric_results(total_latency=1.0), "prod")
        page = render_requests_page(load_recent_requests(self.db_path, "test", 20))
        self.assertIn("No benchmark attempts yet", page)


class ServerTest(DashboardTestCase):
    def start_server(self):
        server = make_server(self.db_path, port=0)
        self.addCleanup(server.server_close)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        return server, f"http://127.0.0.1:{server.server_address[1]}"

    def get(self, url):
        with urllib.request.urlopen(url, timeout=10) as response:
            return response.status, response.headers, response.read().decode("utf-8")

    def test_binds_loopback_and_serves_database_data(self):
        now = datetime.now(timezone.utc)  # the server uses the real clock
        self.save(now - timedelta(minutes=30), 101.0)
        self.save(now - timedelta(minutes=10), 123.4)
        server, base = self.start_server()
        self.assertEqual(HOST, "127.0.0.1")
        self.assertEqual(server.server_address[0], "127.0.0.1")

        status, headers, page = self.get(base + "/")
        self.assertEqual(status, 200)
        self.assertIn("default-src 'none'", headers["Content-Security-Policy"])
        self.assertIn("123.4 ms", page)
        self.assertIn("2 observations in window", visible_text(page))
        self.assertIn(current("7d", "ttft"), page)  # defaults

        status, _, page = self.get(base + "/?window=24h")
        self.assertEqual(status, 200)
        self.assertIn(current("24h", "ttft"), page)

        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(base + "/missing", timeout=10)
        self.assertEqual(ctx.exception.code, 404)

    def test_invalid_window_or_metric_is_400_with_valid_choices(self):
        _, base = self.start_server()
        for query in ("window=%3Cscript%3E", "window=24h&window=7d",
                      "metric=%3Cscript%3E", "metric=ttft&metric=total_latency", "metric="):
            with self.subTest(query=query):
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    urllib.request.urlopen(f"{base}/?{query}", timeout=10)
                self.assertEqual(ctx.exception.code, 400)
                self.assertIn("default-src 'none'", ctx.exception.headers["Content-Security-Policy"])
                page = ctx.exception.read().decode("utf-8")
                self.assertIn("Invalid window or metric", page)
                self.assertIn(link("30d", "ttft"), page)
                self.assertIn(link("7d", "total_latency"), page)
                self.assertNotIn("<script", page)  # the bad value is not echoed

    def test_requests_route(self):
        save_request(self.db_path, REQUEST, metric_results(total_latency=181.4), "test")
        _, base = self.start_server()
        status, headers, page = self.get(base + "/requests")
        self.assertEqual(status, 200)
        self.assertIn("default-src 'none'", headers["Content-Security-Policy"])
        self.assertIn("181.4", page)
        self.assertIn('href="/requests" aria-current="page"', page)
        status, _, page = self.get(base + "/")
        self.assertIn('href="/" aria-current="page"', page)  # aggregate view still default

    def test_empty_database(self):
        _, base = self.start_server()
        status, _, page = self.get(base + "/")
        self.assertEqual(status, 200)
        self.assertIn("observations in the selected window", page)

    def test_port_in_use_fails_clearly(self):
        busy = make_server(self.db_path, port=0)
        self.addCleanup(busy.server_close)
        env = {**os.environ, "LLM_METRICS_DB_PATH": str(self.db_path),
               "LLM_METRICS_PORT": str(busy.server_address[1])}
        proc = subprocess.run(
            [sys.executable, "-m", "llm_metrics.dashboard"],
            cwd=Path(__file__).resolve().parent.parent,
            env=env, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(proc.returncode, 1)
        self.assertIn("already running", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)


if __name__ == "__main__":
    unittest.main()
