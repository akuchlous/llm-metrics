"""Tests for environment-variable configuration.

Every reader is given an explicit mapping, so the real process environment is
never read or changed.
"""

import pathlib
import unittest

from llm_metrics import config
from llm_metrics import providers


class GetAppEnvTest(unittest.TestCase):

    def test_reads_test_and_prod(self):
        self.assertEqual(config.get_app_env({"APP_ENV": "test"}), "test")
        self.assertEqual(config.get_app_env({"APP_ENV": "prod"}), "prod")

    def test_defaults_to_test(self):
        self.assertEqual(config.get_app_env({}), "test")

    def test_invalid_value_fails_clearly(self):
        for bad in ("production", "TEST", "", "dev"):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(
                    config.ConfigError, "Invalid APP_ENV"
                ):
                    config.get_app_env({"APP_ENV": bad})


class GetProviderTest(unittest.TestCase):

    def test_test_env_uses_dummy_provider(self):
        self.assertIsInstance(
            config.get_provider("test"), providers.DummyProvider
        )

    def test_prod_env_refuses_dummy_provider(self):
        with self.assertRaisesRegex(config.ConfigError, "prod"):
            config.get_provider("prod")

    def test_invalid_env_fails_clearly(self):
        with self.assertRaisesRegex(config.ConfigError, "Invalid APP_ENV"):
            config.get_provider("staging")


class GetDbPathTest(unittest.TestCase):

    def test_default_is_data_dir_in_repo(self):
        self.assertEqual(config.get_db_path({}), config.DEFAULT_DB_PATH)
        self.assertEqual(
            config.DEFAULT_DB_PATH.parts[-2:], ("data", "llm_metrics.db")
        )

    def test_override(self):
        self.assertEqual(
            config.get_db_path({"LLM_METRICS_DB_PATH": "/tmp/x.db"}),
            pathlib.Path("/tmp/x.db"),
        )


class GetPortTest(unittest.TestCase):

    def test_default_and_override(self):
        self.assertEqual(config.get_port({}), config.DEFAULT_PORT)
        self.assertEqual(config.get_port({"LLM_METRICS_PORT": "8123"}), 8123)
        self.assertEqual(config.get_port({"LLM_METRICS_PORT": "0"}), 0)

    def test_invalid_port_fails_clearly(self):
        for bad in ("abc", "-1", "70000", "80.5"):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(
                    config.ConfigError, "Invalid LLM_METRICS_PORT"
                ):
                    config.get_port({"LLM_METRICS_PORT": bad})


class GetOriginTest(unittest.TestCase):

    def test_unset_or_empty_is_local_and_deterministic(self):
        self.assertEqual(config.get_origin({}), ("local", "unknown"))
        self.assertEqual(
            config.get_origin(
                {
                    "LLM_METRICS_ORIGIN_CLOUD": "",
                    "LLM_METRICS_ORIGIN_REGION": "",
                }
            ),
            ("local", "unknown"),
        )

    def test_explicit_values(self):
        for cloud, region in (
            ("aws", "us-east-1"),
            ("gcp", "us-central1"),
            ("azure", "eastus"),
        ):
            with self.subTest(cloud=cloud):
                self.assertEqual(
                    config.get_origin(
                        {
                            "LLM_METRICS_ORIGIN_CLOUD": cloud,
                            "LLM_METRICS_ORIGIN_REGION": region,
                        }
                    ),
                    (cloud, region),
                )
        self.assertEqual(
            config.get_origin({"LLM_METRICS_ORIGIN_CLOUD": "aws"}),
            ("aws", "unknown"),
        )

    def test_invalid_values_fail_without_echoing_them(self):
        invalid = ("AWS", "us east 1", "-aws", "aws-", "x" * 64, "a/b", "ünï")
        for bad in invalid:
            for variable in (
                "LLM_METRICS_ORIGIN_CLOUD",
                "LLM_METRICS_ORIGIN_REGION",
            ):
                with self.subTest(variable=variable, bad=bad):
                    with self.assertRaisesRegex(
                        config.ConfigError, f"Invalid {variable}"
                    ) as ctx:
                        config.get_origin({variable: bad})
                    self.assertNotIn(bad, str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
