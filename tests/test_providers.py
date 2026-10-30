import time
import unittest

from llm_metrics.providers import DummyProvider, LLMProvider, Usage, simulated_token_count


def text_and_usage(items):
    items = list(items)
    text = [i for i in items if isinstance(i, str)]
    usage = [i for i in items if isinstance(i, Usage)]
    return text, usage


class SimulatedTokenizerTest(unittest.TestCase):
    def test_one_token_per_four_characters_rounded_up(self):
        self.assertEqual(simulated_token_count(""), 0)
        self.assertEqual(simulated_token_count("abc"), 1)
        self.assertEqual(simulated_token_count("abcd"), 1)
        self.assertEqual(simulated_token_count("abcde"), 2)
        self.assertEqual(simulated_token_count("Say hello."), 3)  # 10 chars

    def test_deterministic(self):
        self.assertEqual(simulated_token_count("Say hello."), simulated_token_count("Say hello."))


class DummyProviderTest(unittest.TestCase):
    def provider(self, **kwargs):
        return DummyProvider(first_token_delay_s=0, inter_token_delay_s=0, **kwargs)

    def test_emits_text_chunks_then_usage_last(self):
        items = list(self.provider(tokens=("a", "b", "c")).stream("hi", 64))
        self.assertEqual(items[:3], ["a", "b", "c"])
        self.assertIsInstance(items[-1], Usage)
        self.assertEqual(len(items), 4)

    def test_usage_counts_tokens_not_chunks(self):
        # Default response: 5 chunks, "This is a dummy response." = 25 chars = 7 tokens.
        text, [usage] = text_and_usage(self.provider().stream("Say hello.", 64))
        self.assertEqual(len(text), 5)
        self.assertEqual(usage, Usage(input_tokens=3, output_tokens=7))

    def test_one_chunk_can_hold_several_tokens(self):
        text, [usage] = text_and_usage(self.provider(tokens=("abcdefghijkl",)).stream("hi", 64))
        self.assertEqual(len(text), 1)
        self.assertEqual(usage.output_tokens, 3)

    def test_stops_before_exceeding_max_output_tokens(self):
        text, [usage] = text_and_usage(self.provider().stream("Say hello.", 3))
        self.assertEqual(text, ["This", " is", " a"])  # " dummy" would make 4 tokens
        self.assertEqual(usage.output_tokens, 3)
        self.assertLessEqual(usage.output_tokens, 3)

    def test_max_output_tokens_must_be_positive(self):
        with self.assertRaises(ValueError):
            list(self.provider().stream("hi", 0))

    def test_inter_token_delay_applies_between_chunks(self):
        provider = DummyProvider(first_token_delay_s=0, inter_token_delay_s=0.02, tokens=("a", "b", "c"))
        started = time.perf_counter()
        list(provider.stream("hi", 64))
        self.assertGreaterEqual(time.perf_counter() - started, 0.04)  # two gaps

    def test_is_an_llm_provider(self):
        provider = DummyProvider()
        self.assertIsInstance(provider, LLMProvider)
        self.assertEqual(provider.name, "dummy")
        self.assertEqual(provider.model, "dummy-model-v1")


if __name__ == "__main__":
    unittest.main()
