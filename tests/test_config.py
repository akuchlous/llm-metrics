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


class GetDatabaseUrlTest(unittest.TestCase):

    def test_fallback_to_sqlite_url_when_not_set(self):
        url = config.get_database_url({})
        self.assertTrue(url.startswith("sqlite:///"), url)
        self.assertIn(str(config.DEFAULT_DB_PATH), url)

    def test_db_path_override_is_reflected_in_url(self):
        url = config.get_database_url({"LLM_METRICS_DB_PATH": "/tmp/custom.db"})
        self.assertEqual(url, "sqlite:////tmp/custom.db")

    def test_explicit_sqlite_url_passes_through(self):
        explicit = "sqlite:////tmp/explicit.db"
        url = config.get_database_url(
            {config.DATABASE_URL_VARIABLE: explicit}
        )
        self.assertEqual(url, explicit)

    def test_postgresql_url_passes_through(self):
        pg_url = "postgresql://user:pass@host:5432/db"
        url = config.get_database_url(
            {config.DATABASE_URL_VARIABLE: pg_url}
        )
        self.assertEqual(url, pg_url)

    def test_postgresql_plus_psycopg2_is_valid(self):
        pg_url = "postgresql+psycopg2://host/db"
        url = config.get_database_url(
            {config.DATABASE_URL_VARIABLE: pg_url}
        )
        self.assertEqual(url, pg_url)

    def test_invalid_scheme_fails_without_echoing_credentials(self):
        bad_url = "mysql://user:secret@host/db"
        with self.assertRaisesRegex(
            config.ConfigError, f"Invalid {config.DATABASE_URL_VARIABLE}"
        ) as ctx:
            config.get_database_url({config.DATABASE_URL_VARIABLE: bad_url})
        error_text = str(ctx.exception)
        self.assertNotIn("mysql://", error_text)
        self.assertNotIn("secret", error_text)

    def test_database_url_takes_precedence_over_db_path(self):
        pg_url = "postgresql://host/db"
        url = config.get_database_url(
            {
                config.DATABASE_URL_VARIABLE: pg_url,
                "LLM_METRICS_DB_PATH": "/tmp/ignored.db",
            }
        )
        self.assertEqual(url, pg_url)

    def test_explicit_environ_not_os_environ(self):
        """get_database_url accepts explicit environ; tests must never rely on os.environ."""
        url = config.get_database_url({})
        self.assertIsInstance(url, str)
        self.assertTrue(url.startswith("sqlite:///"))


if __name__ == "__main__":
    unittest.main()
