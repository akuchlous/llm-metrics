import unittest
from unittest import mock

from llm_metrics import latency
from llm_metrics.latency import METRICS, measure_request
from llm_metrics.providers import DummyProvider, LLMProvider


class ScriptedProvider(LLMProvider):
    """Yields fixed items; counts calls and items consumed."""

    name = "scripted"
    model = "scripted-model"

    def __init__(self, items):
        self.items = items
        self.calls = 0
        self.consumed = 0

    def stream(self, prompt):
        self.calls += 1
        for item in self.items:
            self.consumed += 1
            yield item


def with_clock(readings, provider):
    """Run measure_request with perf_counter returning the given readings (seconds)."""
    with mock.patch.object(latency.time, "perf_counter", side_effect=readings):
        return {r["metric"]: r["value"] for r in measure_request(provider, "hi")}


class MeasureRequestTest(unittest.TestCase):
    def test_result_fields_and_units(self):
        results = measure_request(DummyProvider(first_token_delay_s=0, inter_token_delay_s=0.001), "hi")
        self.assertEqual([r["metric"] for r in results], ["ttft", "total_latency", "output_chunks_per_s"])
        for r in results:
            self.assertEqual((r["provider"], r["model"]), ("dummy", "dummy-model-v1"))
            self.assertGreater(r["value"], 0)
        self.assertEqual(METRICS["output_chunks_per_s"], ("Output throughput", "chunks/s"))
        self.assertEqual(METRICS["ttft"][1], "ms")

    def test_one_provider_call_and_fully_consumed_stream(self):
        provider = ScriptedProvider(["a", "b", "c", "d"])
        results = measure_request(provider, "hi")
        self.assertEqual(provider.calls, 1)
        self.assertEqual(provider.consumed, 4)
        self.assertEqual(len(results), 3)  # all three metrics from that one stream

    def test_exact_values_with_a_controlled_clock(self):
        # start=0; items at 0.100, 0.120, 0.140, 0.160, 0.180; stream ends 0.200 (seconds)
        values = with_clock([0.0, 0.100, 0.120, 0.140, 0.160, 0.180, 0.200],
                            ScriptedProvider(["a", "b", "c", "d", "e"]))
        self.assertAlmostEqual(values["ttft"], 100.0)
        self.assertAlmostEqual(values["total_latency"], 200.0)
        # 4 chunks after the first, over 0.180 - 0.100 = 0.080 s -> 50 chunks/s.
        # Not 5 / 0.2 s (includes TTFT) and not 5 / 0.08 s (counts the first chunk).
        self.assertAlmostEqual(values["output_chunks_per_s"], 50.0)

    def test_empty_items_are_not_output_chunks(self):
        # An empty first item still ends TTFT (unchanged semantics) but is not a chunk.
        values = with_clock([0.0, 0.050, 0.100, 0.120, 0.140, 0.150],
                            ScriptedProvider(["", "a", "", "b"]))
        self.assertAlmostEqual(values["ttft"], 50.0)
        self.assertAlmostEqual(values["total_latency"], 150.0)
        # chunks "a" at 0.100 and "b" at 0.140 -> (2 - 1) / 0.040 s = 25 chunks/s
        self.assertAlmostEqual(values["output_chunks_per_s"], 25.0)

    def test_single_chunk_has_no_throughput(self):
        values = with_clock([0.0, 0.100, 0.110], ScriptedProvider(["only"]))
        self.assertEqual(set(values), {"ttft", "total_latency"})

    def test_only_empty_items_have_no_throughput(self):
        values = with_clock([0.0, 0.100, 0.110, 0.120], ScriptedProvider(["", ""]))
        self.assertEqual(set(values), {"ttft", "total_latency"})

    def test_zero_generation_time_has_no_throughput(self):
        # Two chunks with identical timestamps would be a division by zero.
        values = with_clock([0.0, 0.100, 0.100, 0.100], ScriptedProvider(["a", "b"]))
        self.assertEqual(set(values), {"ttft", "total_latency"})

    def test_ttft_unchanged_and_total_not_earlier(self):
        values = {r["metric"]: r["value"] for r in measure_request(
            DummyProvider(first_token_delay_s=0.05, inter_token_delay_s=0.03, tokens=("a", "b", "c")), "hi")}
        self.assertGreaterEqual(values["ttft"], 50)
        self.assertLess(values["ttft"], 50 + 25)  # excludes the inter-token gaps
        self.assertGreaterEqual(values["total_latency"], 110)  # 50 + 2 x 30 ms
        self.assertGreaterEqual(values["total_latency"], values["ttft"])
        # 2 chunks after the first over >= 60 ms of gaps -> at most ~33.3 chunks/s
        self.assertLessEqual(values["output_chunks_per_s"], 2 / 0.060 + 0.01)

    def test_no_items_raises(self):
        with self.assertRaises(RuntimeError):
            measure_request(ScriptedProvider([]), "hi")


if __name__ == "__main__":
    unittest.main()
