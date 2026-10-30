import unittest

from llm_metrics.pricing import PRICES, Price, price_for, request_cost


class PricingTest(unittest.TestCase):
    def test_dummy_price_is_defined_and_non_zero(self):
        price = price_for("dummy", "dummy-model-v1")
        self.assertEqual(price, Price(input_per_1m=2.00, output_per_1m=8.00))
        self.assertGreater(price.input_per_1m, 0)
        self.assertGreater(price.output_per_1m, 0)

    def test_unknown_model_fails_clearly(self):
        with self.assertRaisesRegex(KeyError, "No price defined"):
            price_for("dummy", "other-model")

    def test_cost_formula_per_1m_tokens(self):
        cost = request_cost(1_000_000, 500_000, Price(input_per_1m=2.0, output_per_1m=8.0))
        self.assertEqual(cost, {"input_cost": 2.0, "output_cost": 4.0, "total_cost": 6.0})

    def test_small_request_keeps_full_precision(self):
        # 3 input and 7 output tokens: 3 * 2 / 1e6 + 7 * 8 / 1e6 = 0.000062 USD,
        # far below a cent; nothing is rounded before storage.
        cost = request_cost(3, 7, PRICES[("dummy", "dummy-model-v1")])
        self.assertAlmostEqual(cost["input_cost"], 0.000006, places=15)
        self.assertAlmostEqual(cost["output_cost"], 0.000056, places=15)
        self.assertAlmostEqual(cost["total_cost"], 0.000062, places=15)
        self.assertEqual(cost["total_cost"], cost["input_cost"] + cost["output_cost"])

    def test_zero_tokens_cost_nothing(self):
        cost = request_cost(0, 0, Price(input_per_1m=2.0, output_per_1m=8.0))
        self.assertEqual(cost["total_cost"], 0.0)


if __name__ == "__main__":
    unittest.main()
