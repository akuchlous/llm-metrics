import random
import unittest

from llm_metrics.percentiles import percentile


class NearestRankPercentileTest(unittest.TestCase):
    def test_known_small_dataset(self):
        values = [15, 20, 35, 40, 50]
        self.assertEqual(percentile(values, 30), 20)  # rank ceil(1.5) = 2
        self.assertEqual(percentile(values, 50), 35)  # rank ceil(2.5) = 3
        self.assertEqual(percentile(values, 95), 50)  # rank ceil(4.75) = 5
        self.assertEqual(percentile(values, 100), 50)

    def test_twenty_values(self):
        values = list(range(1, 21))
        self.assertEqual(percentile(values, 50), 10)  # rank 10
        self.assertEqual(percentile(values, 95), 19)  # rank 19
        self.assertEqual(percentile(values, 99), 20)  # rank ceil(19.8) = 20

    def test_hundred_values_exact_ranks(self):
        values = list(range(1, 101))
        for p in (1, 7, 50, 95, 99, 100):  # 7 * 100 / 100 must be rank 7, not 8
            self.assertEqual(percentile(values, p), p)

    def test_independent_of_input_order(self):
        values = [float(v) for v in range(1, 201)]
        shuffled = values[:]
        random.Random(1).shuffle(shuffled)
        for p in (50, 95, 99):
            self.assertEqual(percentile(shuffled, p), percentile(values, p))

    def test_single_value(self):
        for p in (50, 95, 99):
            self.assertEqual(percentile([42.0], p), 42.0)

    def test_empty_values_rejected(self):
        with self.assertRaisesRegex(ValueError, "no values"):
            percentile([], 50)

    def test_out_of_range_p_rejected(self):
        for p in (0, 101, -5):
            with self.subTest(p=p):
                with self.assertRaises(ValueError):
                    percentile([1.0], p)


if __name__ == "__main__":
    unittest.main()
