import time
import unittest

from llm_metrics.providers import DummyProvider, LLMProvider


class DummyProviderTest(unittest.TestCase):
    def test_emits_tokens(self):
        provider = DummyProvider(first_token_delay_s=0, tokens=("a", "b", "c"))
        self.assertEqual(list(provider.stream("hi")), ["a", "b", "c"])

    def test_inter_token_delay_applies_between_tokens(self):
        provider = DummyProvider(first_token_delay_s=0, inter_token_delay_s=0.02, tokens=("a", "b", "c"))
        started = time.perf_counter()
        self.assertEqual(list(provider.stream("hi")), ["a", "b", "c"])
        self.assertGreaterEqual(time.perf_counter() - started, 0.04)  # two gaps

    def test_default_tokens_are_not_empty(self):
        provider = DummyProvider(first_token_delay_s=0)
        self.assertGreater(len(list(provider.stream("hi"))), 0)

    def test_is_an_llm_provider(self):
        provider = DummyProvider()
        self.assertIsInstance(provider, LLMProvider)
        self.assertEqual(provider.name, "dummy")
        self.assertEqual(provider.model, "dummy-model-v1")


if __name__ == "__main__":
    unittest.main()
