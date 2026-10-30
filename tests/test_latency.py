import unittest
from unittest import mock

from llm_metrics import latency
from llm_metrics.latency import METRICS, measure_request
from llm_metrics.outcomes import FAILURE_CATEGORIES
from llm_metrics.providers import DummyProvider, LLMProvider, ProviderFailure, Usage

DEFAULT_USAGE = Usage(input_tokens=2, output_tokens=5)


class ScriptedProvider(LLMProvider):
    """Yields fixed items (text chunks and/or Usage); counts calls and items consumed."""

    name = "scripted"
    model = "scripted-model"

    def __init__(self, items):
        self.items = items
        self.calls = 0
        self.consumed = 0

    def stream(self, prompt, max_output_tokens):
        self.calls += 1
        for item in self.items:
            self.consumed += 1
            yield item


def with_clock(readings, provider, max_output_tokens=64):
    """Run measure_request with perf_counter returning the given readings (seconds):
    one at the start, one per streamed item (including Usage), one at the end."""
    with mock.patch.object(latency.time, "perf_counter", side_effect=readings):
        request, results = measure_request(provider, "hi", max_output_tokens)
    return request, {r["metric"]: r["value"] for r in results}


class MeasureRequestTest(unittest.TestCase):
    def test_result_fields_and_units(self):
        request, results = measure_request(
            DummyProvider(first_token_delay_s=0, inter_token_delay_s=0.001), "Say hello.", 64
        )
        self.assertEqual([r["metric"] for r in results], ["total_latency", "ttft", "output_chunks_per_s"])
        for r in results:
            self.assertEqual((r["provider"], r["model"]), ("dummy", "dummy-model-v1"))
            self.assertGreater(r["value"], 0)
        self.assertEqual(METRICS["output_chunks_per_s"], ("Output throughput", "chunks/s"))
        self.assertEqual(list(METRICS)[0], "total_latency")  # primary latency first

    def test_token_facts_come_from_usage_not_chunk_count(self):
        request, results = measure_request(
            DummyProvider(first_token_delay_s=0, inter_token_delay_s=0.001), "Say hello.", 64
        )
        self.assertEqual(request, {
            "provider": "dummy", "model": "dummy-model-v1",
            "outcome": "success",
            "input_tokens": 3,                    # deterministic: "Say hello." = 10 chars
            "requested_max_output_tokens": 64,    # the cap we asked for
            "output_tokens": 7,                   # what was generated: 25 chars
            "failed_after_ms": None,
            "provider_request_id": None,          # the dummy provider has none
        })
        # 5 chunks were streamed, yet 7 tokens are reported.
        self.assertNotEqual(request["output_tokens"], 5)

    def test_one_provider_call_and_fully_consumed_stream(self):
        provider = ScriptedProvider(["a", "b", "c", "d", DEFAULT_USAGE])
        request, results = measure_request(provider, "hi", 64)
        self.assertEqual(provider.calls, 1)
        self.assertEqual(provider.consumed, 5)
        self.assertEqual(len(results), 3)
        self.assertEqual(request["output_tokens"], 5)  # from Usage: 4 chunks, 5 tokens

    def test_exact_values_with_a_controlled_clock(self):
        # start=0; chunks at 0.100..0.180, usage at 0.190, stream ends 0.200 (seconds)
        request, values = with_clock(
            [0.0, 0.100, 0.120, 0.140, 0.160, 0.180, 0.190, 0.200],
            ScriptedProvider(["a", "b", "c", "d", "e", DEFAULT_USAGE]),
        )
        self.assertAlmostEqual(values["ttft"], 100.0)
        self.assertAlmostEqual(values["total_latency"], 200.0)
        # 4 chunks after the first over 0.180 - 0.100 = 0.080 s -> 50 chunks/s.
        self.assertAlmostEqual(values["output_chunks_per_s"], 50.0)

    def test_empty_items_are_not_output_chunks(self):
        # An empty first item still ends TTFT (unchanged semantics) but is not a chunk.
        _, values = with_clock([0.0, 0.050, 0.100, 0.120, 0.140, 0.145, 0.150],
                               ScriptedProvider(["", "a", "", "b", DEFAULT_USAGE]))
        self.assertAlmostEqual(values["ttft"], 50.0)
        self.assertAlmostEqual(values["total_latency"], 150.0)
        self.assertAlmostEqual(values["output_chunks_per_s"], 25.0)

    def test_single_chunk_has_no_throughput(self):
        _, values = with_clock([0.0, 0.100, 0.105, 0.110], ScriptedProvider(["only", DEFAULT_USAGE]))
        self.assertEqual(set(values), {"ttft", "total_latency"})

    def test_zero_generation_time_has_no_throughput(self):
        _, values = with_clock([0.0, 0.100, 0.100, 0.100, 0.100],
                               ScriptedProvider(["a", "b", DEFAULT_USAGE]))
        self.assertEqual(set(values), {"ttft", "total_latency"})

    def test_ttft_unchanged_and_total_not_earlier(self):
        _, results = measure_request(
            DummyProvider(first_token_delay_s=0.05, inter_token_delay_s=0.03, tokens=("a", "b", "c")),
            "hi", 64,
        )
        values = {r["metric"]: r["value"] for r in results}
        self.assertGreaterEqual(values["ttft"], 50)
        self.assertLess(values["ttft"], 50 + 25)  # excludes the inter-chunk gaps
        self.assertGreaterEqual(values["total_latency"], 110)  # 50 + 2 x 30 ms
        self.assertGreaterEqual(values["total_latency"], values["ttft"])

    def assert_failed(self, provider, category, max_output_tokens=64):
        attempt, results = measure_request(provider, "hi", max_output_tokens)
        self.assertEqual(attempt["outcome"], category)
        # Unknown facts are None, never 0; no partial metrics are kept.
        self.assertIsNone(attempt["input_tokens"])
        self.assertIsNone(attempt["output_tokens"])
        self.assertEqual(results, [])
        self.assertEqual(attempt["requested_max_output_tokens"], max_output_tokens)
        self.assertGreaterEqual(attempt["failed_after_ms"], 0)
        return attempt

    def test_simulated_provider_failures_map_to_their_category(self):
        for category in ("timeout", "rate_limited", "provider_error", "transport_error"):
            for after in (0, 2):  # before any text, and after some text
                with self.subTest(category=category, fail_after_chunks=after):
                    self.assert_failed(
                        DummyProvider(first_token_delay_s=0, inter_token_delay_s=0,
                                      fail_with=category, fail_after_chunks=after),
                        category,
                    )

    def test_every_category_is_raisable_and_unknown_ones_are_rejected(self):
        for category in FAILURE_CATEGORIES:
            self.assertEqual(ProviderFailure(category).category, category)
        with self.assertRaises(ValueError):
            ProviderFailure("http_503")  # provider-specific codes must be mapped first

    def test_missing_usage_is_invalid_response(self):
        self.assert_failed(DummyProvider(first_token_delay_s=0, inter_token_delay_s=0, omit_usage=True),
                           "invalid_response")
        self.assert_failed(ScriptedProvider(["a", "b"]), "invalid_response")

    def test_no_text_is_invalid_response(self):
        self.assert_failed(ScriptedProvider([DEFAULT_USAGE]), "invalid_response")

    def test_duplicate_usage_is_invalid_response(self):
        self.assert_failed(ScriptedProvider(["a", DEFAULT_USAGE, DEFAULT_USAGE]), "invalid_response")

    def test_text_after_usage_is_invalid_response(self):
        self.assert_failed(ScriptedProvider(["a", DEFAULT_USAGE, "b"]), "invalid_response")

    def test_output_tokens_above_requested_max_is_invalid_response(self):
        self.assert_failed(ScriptedProvider(["a", Usage(1, 10)]), "invalid_response", max_output_tokens=5)

    def test_failed_after_is_time_until_failure_detected(self):
        # start=0; chunk at 0.100; failure raised; caught at 0.250 (seconds)
        class FailsAfterOneChunk(LLMProvider):
            name, model = "f", "f-model"

            def stream(self, prompt, max_output_tokens):
                yield "a"
                raise ProviderFailure("timeout")

        with mock.patch.object(latency.time, "perf_counter", side_effect=[0.0, 0.100, 0.250]):
            attempt, results = measure_request(FailsAfterOneChunk(), "hi", 64)
        self.assertEqual(attempt["outcome"], "timeout")
        self.assertAlmostEqual(attempt["failed_after_ms"], 250.0)
        self.assertEqual(results, [])  # the TTFT seen at 0.100 is not kept

    def test_unexpected_exceptions_are_not_recorded_as_provider_failures(self):
        class Buggy(LLMProvider):
            name, model = "b", "b-model"

            def stream(self, prompt, max_output_tokens):
                raise KeyError("bug in llm-metrics, not a provider failure")
                yield  # pragma: no cover

        with self.assertRaises(KeyError):
            measure_request(Buggy(), "hi", 64)

if __name__ == "__main__":
    unittest.main()
