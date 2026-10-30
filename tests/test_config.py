import unittest

from pathlib import Path

from llm_metrics.config import (
    DEFAULT_DB_PATH,
    DEFAULT_PORT,
    ConfigError,
    get_app_env,
    get_db_path,
    get_port,
    get_provider,
)
from llm_metrics.providers import DummyProvider


class GetAppEnvTest(unittest.TestCase):
    def test_reads_test_and_prod(self):
        self.assertEqual(get_app_env({"APP_ENV": "test"}), "test")
        self.assertEqual(get_app_env({"APP_ENV": "prod"}), "prod")

    def test_defaults_to_test(self):
        self.assertEqual(get_app_env({}), "test")

    def test_invalid_value_fails_clearly(self):
        for bad in ("production", "TEST", "", "dev"):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(ConfigError, "Invalid APP_ENV"):
                    get_app_env({"APP_ENV": bad})


class GetProviderTest(unittest.TestCase):
    def test_test_env_uses_dummy_provider(self):
        self.assertIsInstance(get_provider("test"), DummyProvider)

    def test_prod_env_refuses_dummy_provider(self):
        with self.assertRaisesRegex(ConfigError, "prod"):
            get_provider("prod")

    def test_invalid_env_fails_clearly(self):
        with self.assertRaisesRegex(ConfigError, "Invalid APP_ENV"):
            get_provider("staging")


class GetDbPathTest(unittest.TestCase):
    def test_default_is_data_dir_in_repo(self):
        self.assertEqual(get_db_path({}), DEFAULT_DB_PATH)
        self.assertEqual(DEFAULT_DB_PATH.parts[-2:], ("data", "llm_metrics.db"))

    def test_override(self):
        self.assertEqual(
            get_db_path({"LLM_METRICS_DB_PATH": "/tmp/x.db"}), Path("/tmp/x.db")
        )


class GetPortTest(unittest.TestCase):
    def test_default_and_override(self):
        self.assertEqual(get_port({}), DEFAULT_PORT)
        self.assertEqual(get_port({"LLM_METRICS_PORT": "8123"}), 8123)
        self.assertEqual(get_port({"LLM_METRICS_PORT": "0"}), 0)

    def test_invalid_port_fails_clearly(self):
        for bad in ("abc", "-1", "70000", "80.5"):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(ConfigError, "Invalid LLM_METRICS_PORT"):
                    get_port({"LLM_METRICS_PORT": bad})


if __name__ == "__main__":
    unittest.main()
