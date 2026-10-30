"""Tests for the Flask HTTP boundary (`llm_metrics.web`).

Routes are exercised through Flask's test client against a temporary
database, with outgoing network access blocked: no web test can reach a
provider or spend money. Two tests start the real server process on
127.0.0.1 to check serving and the busy-port message.
"""

import ast
import datetime
import os
import pathlib
import re
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import urllib.request

from llm_metrics import config
from llm_metrics import dashboard
from llm_metrics import latency
from llm_metrics import storage
from llm_metrics import web

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CSP = "default-src 'none'; style-src 'unsafe-inline'"

SIMULATED_REQUEST = {
    "provider": "dummy",
    "model": "dummy-model-v1",
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
REAL_REQUEST = {
    **SIMULATED_REQUEST,
    "provider": "openai",
    "model": "gpt-6-luna",
    "workload_id": "smoke.short_text.v2",
    "cache_policy": "disabled",
    "input_price_per_1m": 0.10,
    "output_price_per_1m": 0.50,
    "input_cost": 3e-07,
    "output_cost": 3.5e-06,
    "total_cost": 3.8e-06,
}


def _blocked(*args, **kwargs):
    raise AssertionError("network access attempted")


def aria_current(href):
    return f'href="{href}" aria-current="page"'


class WebTestCase(unittest.TestCase):
    """Gives each test an app on its own database, with the network blocked."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db_path = pathlib.Path(tmp.name) / "data" / "llm_metrics.db"
        self.app = web.create_app(self.db_path)
        self.client = self.app.test_client()
        for target in ("socket.socket.connect", "urllib.request.urlopen"):
            patcher = mock.patch(target, side_effect=_blocked)
            self.addCleanup(patcher.stop)
            patcher.start()

    def get(self, path):
        response = self.client.get(path)
        return response, response.get_data(as_text=True)

    def assert_html_with_csp(self, response, status):
        self.assertEqual(response.status_code, status)
        self.assertEqual(response.mimetype, "text/html")
        self.assertEqual(response.headers["Content-Security-Policy"], CSP)

    def save_observation(self, minutes_ago, value, metric="ttft"):
        # The app uses the real clock, so data is placed relative to now.
        recorded_at = datetime.datetime.now(
            datetime.timezone.utc
        ) - datetime.timedelta(minutes=minutes_ago)
        storage.save_new_observations(
            self.db_path,
            [
                (
                    recorded_at,
                    {
                        "provider": "dummy",
                        "model": "dummy-model-v1",
                        "metric": metric,
                        "value": value,
                    },
                )
            ],
            "test",
        )


class AggregateRouteTest(WebTestCase):

    def test_defaults_and_database_data(self):
        self.save_observation(30, 101.0)
        self.save_observation(10, 123.4)
        response, page = self.get("/")
        self.assert_html_with_csp(response, 200)
        self.assertIn("123.4 ms", page)
        self.assertIn("2 observations in window", page)
        self.assertIn(aria_current("/?window=7d&amp;metric=ttft"), page)
        self.assertIn("TEST / SIMULATED DATA", page)

    def test_every_valid_window_and_metric(self):
        for window in dashboard.WINDOWS:
            for metric in latency.METRICS:
                with self.subTest(window=window, metric=metric):
                    response, page = self.get(
                        f"/?window={window}&metric={metric}"
                    )
                    self.assert_html_with_csp(response, 200)
                    self.assertIn(
                        aria_current(f"/?window={window}&amp;metric={metric}"),
                        page,
                    )

    def test_unrelated_parameters_are_ignored(self):
        response, page = self.get("/?window=24h&utm_source=x")
        self.assert_html_with_csp(response, 200)
        self.assertIn(aria_current("/?window=24h&amp;metric=ttft"), page)

    def test_invalid_query_is_400_and_never_echoed(self):
        for query in (
            "window=%3Cscript%3E",
            "window=24h&window=7d",
            "window=",
            "window",
            "metric=%3Cscript%3E",
            "metric=ttft&metric=total_latency",
            "metric=",
        ):
            with self.subTest(query=query):
                response, page = self.get(f"/?{query}")
                self.assert_html_with_csp(response, 400)
                self.assertIn("Invalid window or metric", page)
                self.assertIn('href="/?window=30d&amp;metric=ttft"', page)
                self.assertNotIn("<script", page)


class RequestsRouteTest(WebTestCase):

    def setUp(self):
        super().setUp()
        self.simulated_id = storage.save_request(
            self.db_path, SIMULATED_REQUEST, [], "test"
        )
        self.real_id = storage.save_request(
            self.db_path, REAL_REQUEST, [], "prod"
        )

    def test_simulated_population_by_default(self):
        response, page = self.get("/requests")
        self.assert_html_with_csp(response, 200)
        self.assertIn("TEST / SIMULATED DATA", page)
        self.assertIn(self.simulated_id[:8], page)
        self.assertNotIn(self.real_id[:8], page)
        self.assertIn(aria_current("/requests"), page)
        self.assertIn(aria_current("/requests?data=simulated"), page)

    def test_real_population(self):
        response, page = self.get("/requests?data=real")
        self.assert_html_with_csp(response, 200)
        self.assertIn("REAL PROVIDER DATA", page)
        self.assertNotIn("TEST / SIMULATED DATA", page)
        self.assertIn(self.real_id[:8], page)
        self.assertNotIn(self.simulated_id[:8], page)
        self.assertIn("smoke.short_text.v2", page)

    def test_invalid_data_is_400(self):
        for query in ("data=prod", "data=", "data=real&data=simulated"):
            with self.subTest(query=query):
                response, page = self.get(f"/requests?{query}")
                self.assert_html_with_csp(response, 400)
                self.assertNotIn("prod</", page)


class SpendRouteTest(WebTestCase):

    def test_default_window_and_real_data_only(self):
        storage.save_request(self.db_path, SIMULATED_REQUEST, [], "test")
        storage.save_request(self.db_path, REAL_REQUEST, [], "prod")
        response, page = self.get("/spend")
        self.assert_html_with_csp(response, 200)
        self.assertIn(aria_current("/spend?window=30d"), page)
        self.assertIn(aria_current("/spend"), page)
        self.assertIn("REAL PROVIDER DATA", page)
        self.assertIn("gpt-6-luna", page)
        self.assertNotIn("dummy-model-v1", page)  # simulated cost never shown

    def test_valid_and_invalid_windows(self):
        for window in dashboard.WINDOWS:
            with self.subTest(window=window):
                response, page = self.get(f"/spend?window={window}")
                self.assert_html_with_csp(response, 200)
                self.assertIn(aria_current(f"/spend?window={window}"), page)
        for query in ("window=1y", "window=7d&window=30d", "window="):
            with self.subTest(query=query):
                response, _ = self.get(f"/spend?{query}")
                self.assert_html_with_csp(response, 400)


class RoutingTest(WebTestCase):

    def test_unknown_paths_are_404_with_csp(self):
        for path in ("/missing", "/requests/", "/spend/x", "/static/x.css"):
            with self.subTest(path=path):
                response, _ = self.get(path)
                self.assertEqual(response.status_code, 404)
                self.assertEqual(
                    response.headers["Content-Security-Policy"], CSP
                )

    def test_only_get_is_allowed(self):
        for path in ("/", "/requests", "/spend"):
            with self.subTest(path=path):
                self.assertEqual(self.client.post(path).status_code, 405)

    def test_no_network_access_while_serving_pages(self):
        storage.save_request(self.db_path, REAL_REQUEST, [], "prod")
        for path in ("/", "/requests", "/requests?data=real", "/spend"):
            self.assertEqual(self.client.get(path).status_code, 200)
        # setUp's patches raise on any connection, so reaching this line means
        # no route opened one.


class AppFactoryTest(unittest.TestCase):

    def test_uses_the_given_database_and_creates_it_only_on_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = pathlib.Path(tmp) / "data" / "isolated.db"
            app = web.create_app(db_path)
            self.assertEqual(app.config[web.DB_PATH_KEY], db_path)
            self.assertFalse(db_path.exists())  # no work at creation time
            self.assertEqual(app.test_client().get("/").status_code, 200)
            self.assertTrue(db_path.exists())

    def test_default_database_path_is_read_when_the_app_is_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = pathlib.Path(tmp) / "from-env.db"
            with mock.patch.dict(
                os.environ, {"LLM_METRICS_DB_PATH": str(db_path)}
            ):
                app = web.create_app()
            self.assertEqual(app.config[web.DB_PATH_KEY], db_path)
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LLM_METRICS_DB_PATH", None)
            self.assertEqual(
                web.create_app().config[web.DB_PATH_KEY],
                config.DEFAULT_DB_PATH,
            )

    def test_debug_mode_is_never_enabled(self):
        with mock.patch.dict(os.environ, {"FLASK_DEBUG": "1"}):
            app = web.create_app(pathlib.Path("unused.db"))
        self.assertFalse(app.debug)
        self.assertEqual(web.HOST, "127.0.0.1")

    def test_errors_do_not_expose_stack_traces(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = web.create_app(pathlib.Path(tmp) / "x.db")
            with mock.patch.object(
                dashboard, "build_page", side_effect=RuntimeError("secret-xyz")
            ), self.assertLogs(app.logger, level="ERROR") as logs:
                response = app.test_client().get("/")
        # The error is logged on the server, not sent to the browser.
        self.assertIn("secret-xyz", "\n".join(logs.output))
        self.assertEqual(response.status_code, 500)
        body = response.get_data(as_text=True)
        self.assertNotIn("secret-xyz", body)
        self.assertNotIn("Traceback", body)


def run_python(code, env_overrides=None, timeout=30):
    env = {**os.environ, **(env_overrides or {})}
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


class ImportAndDependencyTest(unittest.TestCase):

    def test_importing_web_starts_nothing_and_touches_no_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = pathlib.Path(tmp) / "untouched.db"
            proc = run_python(
                "import llm_metrics.web, llm_metrics.dashboard",
                {"LLM_METRICS_DB_PATH": str(db_path)},
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(proc.stdout, "")
            self.assertFalse(db_path.exists())

    def test_only_the_web_module_imports_flask_or_werkzeug(self):
        for path in sorted((REPO_ROOT / "llm_metrics").glob("*.py")):
            if path.name == "web.py":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported |= {
                        alias.name.split(".")[0] for alias in node.names
                    }
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
            with self.subTest(module=path.name):
                self.assertFalse(imported & {"flask", "werkzeug"})

    def test_benchmark_and_data_layers_load_without_flask(self):
        modules = (
            "benchmark",
            "config",
            "dashboard",
            "latency",
            "openai_provider",
            "outcomes",
            "percentiles",
            "pricing",
            "providers",
            "real_smoke",
            "seed_history",
            "storage",
            "__main__",
        )
        code = (
            "import importlib, sys\n"
            f"for name in {modules!r}:\n"
            "    importlib.import_module('llm_metrics.' + name)\n"
            "loaded = sorted(m for m in sys.modules\n"
            "                if m.split('.')[0] in ('flask', 'werkzeug'))\n"
            "print(loaded)\n"
        )
        proc = run_python(code)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "[]")


class ServerProcessTest(unittest.TestCase):
    """Runs `python -m llm_metrics.web` for real, on 127.0.0.1 only."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.env = {
            **os.environ,
            "LLM_METRICS_DB_PATH": str(pathlib.Path(tmp.name) / "x.db"),
        }

    def test_serves_pages_on_loopback(self):
        proc = subprocess.Popen(
            [sys.executable, "-m", "llm_metrics.web"],
            cwd=REPO_ROOT,
            env={**self.env, "LLM_METRICS_PORT": "0"},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            line = proc.stdout.readline()
            match = re.match(r"Dashboard: (http://127\.0\.0\.1:\d+/) ", line)
            self.assertIsNotNone(match, line)
            with urllib.request.urlopen(match.group(1), timeout=10) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(
                    response.headers["Content-Security-Policy"], CSP
                )
                self.assertIn("TEST / SIMULATED DATA", response.read().decode())
        finally:
            proc.terminate()
            proc.wait(timeout=10)
            proc.stdout.close()
            proc.stderr.close()

    def test_port_in_use_fails_clearly(self):
        with socket.create_server(("127.0.0.1", 0)) as busy:
            port = busy.getsockname()[1]
            proc = subprocess.run(
                [sys.executable, "-m", "llm_metrics.web"],
                cwd=REPO_ROOT,
                env={**self.env, "LLM_METRICS_PORT": str(port)},
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        self.assertEqual(proc.returncode, 1)
        self.assertIn("already running", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)

    def test_invalid_port_is_a_configuration_error(self):
        proc = subprocess.run(
            [sys.executable, "-m", "llm_metrics.web"],
            cwd=REPO_ROOT,
            env={**self.env, "LLM_METRICS_PORT": "99999"},
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("Invalid LLM_METRICS_PORT", proc.stderr)


if __name__ == "__main__":
    unittest.main()
