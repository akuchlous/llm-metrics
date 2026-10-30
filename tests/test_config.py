import unittest

from llm_metrics.config import ConfigError, get_app_env, get_provider
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


if __name__ == "__main__":
    unittest.main()
