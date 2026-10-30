import unittest

from llm_metrics.latency import measure_latency
from llm_metrics.providers import DummyProvider, LLMProvider


class EmptyProvider(LLMProvider):
    name = "empty"
    model = "empty-model"

    def stream(self, prompt):
        return iter(())


class CountingProvider(DummyProvider):
    """DummyProvider that records how often stream() is called and consumed."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.calls = 0
        self.tokens_yielded = 0

    def stream(self, prompt):
        self.calls += 1
        for token in super().stream(prompt):
            self.tokens_yielded += 1
            yield token


class MeasureLatencyTest(unittest.TestCase):
    def test_result_fields(self):
        ttft, total = measure_latency(DummyProvider(first_token_delay_s=0, inter_token_delay_s=0), "hi")
        for result, metric in ((ttft, "ttft"), (total, "total_latency")):
            self.assertEqual(result["provider"], "dummy")
            self.assertEqual(result["model"], "dummy-model-v1")
            self.assertEqual(result["metric"], metric)
            self.assertGreater(result["value_ms"], 0)

    def test_one_request_fully_consumed(self):
        provider = CountingProvider(first_token_delay_s=0, inter_token_delay_s=0, tokens=("a", "b", "c"))
        measure_latency(provider, "hi")
        self.assertEqual(provider.calls, 1)
        self.assertEqual(provider.tokens_yielded, 3)

    def test_total_is_never_earlier_than_ttft(self):
        for inter in (0, 0.005):
            with self.subTest(inter_token_delay_s=inter):
                ttft, total = measure_latency(
                    DummyProvider(first_token_delay_s=0, inter_token_delay_s=inter), "hi"
                )
                self.assertGreaterEqual(total["value_ms"], ttft["value_ms"])

    def test_ttft_reflects_first_token_delay_only(self):
        # TTFT semantics are unchanged: later token delays must not affect it.
        ttft, total = measure_latency(
            DummyProvider(first_token_delay_s=0.05, inter_token_delay_s=0.03, tokens=("a", "b", "c")),
            "hi",
        )
        self.assertGreaterEqual(ttft["value_ms"], 50)
        self.assertLess(ttft["value_ms"], 50 + 25)  # well below the first inter-token gap
        # total = 50 ms + 2 gaps of 30 ms; time.sleep never returns early.
        self.assertGreaterEqual(total["value_ms"], 110)
        self.assertLess(total["value_ms"], 110 + 200)

    def test_single_token_total_close_to_ttft(self):
        ttft, total = measure_latency(
            DummyProvider(first_token_delay_s=0.02, inter_token_delay_s=0.5, tokens=("only",)), "hi"
        )
        self.assertLess(total["value_ms"] - ttft["value_ms"], 50)  # no inter-token wait

    def test_no_tokens_raises(self):
        with self.assertRaises(RuntimeError):
            measure_latency(EmptyProvider(), "hi")


if __name__ == "__main__":
    unittest.main()
