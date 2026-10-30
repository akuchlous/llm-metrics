import os
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from llm_metrics.dashboard import HOST, make_server, render_page
from llm_metrics.storage import load_observations, save_new_observations

DUMMY = {"provider": "dummy", "model": "dummy-model-v1", "metric": "ttft"}


def at(hour):
    return datetime(2026, 10, 23, hour, tzinfo=timezone.utc)


class DashboardTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db_path = Path(tmp.name) / "observations.db"

    def save(self, hour, value_ms, environment="test", **overrides):
        result = {**DUMMY, "value_ms": value_ms, **overrides}
        save_new_observations(self.db_path, [(at(hour), result)], environment)

    def test_load_filters_and_orders_by_time(self):
        self.save(5, 105.0)
        self.save(1, 101.0)
        self.save(3, 103.0)
        self.save(2, 999.0, environment="prod")
        self.save(2, 999.0, provider="other")
        self.save(2, 999.0, model="other-model")
        self.save(2, 999.0, metric="other_metric")
        rows = load_observations(self.db_path, "test", "dummy", "dummy-model-v1", "ttft")
        self.assertEqual(
            rows,
            [
                ("2026-10-23T01:00:00.000000Z", 101.0),
                ("2026-10-23T03:00:00.000000Z", 103.0),
                ("2026-10-23T05:00:00.000000Z", 105.0),
            ],
        )

    def test_page_shows_label_provider_latest_and_chart(self):
        page = render_page([("2026-10-23T01:00:00.000000Z", 101.0),
                            ("2026-10-23T02:00:00.000000Z", 123.4)])
        self.assertIn("TEST / SIMULATED DATA", page)
        self.assertIn("dummy", page)
        self.assertIn("dummy-model-v1", page)
        self.assertIn("123.4 ms", page)
        self.assertIn("2026-10-23 02:00 UTC", page)
        self.assertIn("<polyline", page)
        self.assertNotIn("last 7 days", page.lower())

    def test_single_observation_renders(self):
        page = render_page([("2026-10-23T01:00:00.000000Z", 101.0)])
        self.assertIn("101.0 ms", page)
        self.assertIn("<svg", page)

    def test_empty_data_renders_valid_page(self):
        page = render_page([])
        self.assertIn("TEST / SIMULATED DATA", page)
        self.assertIn("No observations yet", page)
        self.assertNotIn("<svg", page)
        self.assertTrue(page.rstrip().endswith("</html>"))

    def test_server_binds_loopback_and_serves_database_data(self):
        self.save(1, 101.0)
        self.save(2, 123.4)
        server = make_server(self.db_path, port=0)
        self.addCleanup(server.server_close)
        self.assertEqual(HOST, "127.0.0.1")
        self.assertEqual(server.server_address[0], "127.0.0.1")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)
        base = f"http://127.0.0.1:{server.server_address[1]}"

        with urllib.request.urlopen(base + "/", timeout=10) as response:
            self.assertEqual(response.status, 200)
            self.assertIn("default-src 'none'", response.headers["Content-Security-Policy"])
            page = response.read().decode("utf-8")
        self.assertIn("123.4 ms", page)  # the latest value from SQLite
        self.assertIn("All 2 observations", page)

        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(base + "/missing", timeout=10)
        self.assertEqual(ctx.exception.code, 404)

    def test_server_with_empty_database(self):
        server = make_server(self.db_path, port=0)
        self.addCleanup(server.server_close)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        url = f"http://127.0.0.1:{server.server_address[1]}/"
        with urllib.request.urlopen(url, timeout=10) as response:
            self.assertEqual(response.status, 200)
            self.assertIn("No observations yet", response.read().decode("utf-8"))

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
