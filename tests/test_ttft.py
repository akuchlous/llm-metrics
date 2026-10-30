import unittest

from llm_metrics.providers import DummyProvider, LLMProvider
from llm_metrics.ttft import measure_ttft


class EmptyProvider(LLMProvider):
    name = "empty"
    model = "empty-model"

    def stream(self, prompt):
        return iter(())


class MeasureTTFTTest(unittest.TestCase):
    def test_result_fields(self):
        result = measure_ttft(DummyProvider(first_token_delay_s=0), "hi")
        self.assertEqual(result["provider"], "dummy")
        self.assertEqual(result["model"], "dummy-model-v1")
        self.assertEqual(result["metric"], "ttft")

    def test_value_is_positive(self):
        result = measure_ttft(DummyProvider(first_token_delay_s=0), "hi")
        self.assertGreater(result["value_ms"], 0)

    def test_value_reflects_configured_delay(self):
        delay_ms = 50
        result = measure_ttft(DummyProvider(first_token_delay_s=delay_ms / 1000), "hi")
        # time.sleep waits at least the requested time; allow generous scheduling slack.
        self.assertGreaterEqual(result["value_ms"], delay_ms)
        self.assertLess(result["value_ms"], delay_ms + 200)

    def test_no_tokens_raises(self):
        with self.assertRaises(RuntimeError):
            measure_ttft(EmptyProvider(), "hi")


if __name__ == "__main__":
    unittest.main()
