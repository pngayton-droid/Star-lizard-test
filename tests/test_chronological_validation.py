"""No-network regression tests for Starlizard research utilities."""
import unittest
from research.chronological_validation import (
    chronological_split, chronological_three_way_split, evaluate_binary_baseline, wilson_interval,
)


class ChronologicalValidationTests(unittest.TestCase):
    def test_wilson(self):
        self.assertEqual(wilson_interval(0, 0), (None, None))
        lo, hi = wilson_interval(50, 100)
        self.assertLess(lo, 0.5)
        self.assertGreater(hi, 0.5)

    def test_never_split_a_calendar_day(self):
        rows = [
            {"match_id": str(i), "match_date": f"2026-01-{i//3+1:02d}", "outcome": i % 2}
            for i in range(30)
        ]
        train, test, cutoff = chronological_split(rows, 0.7)
        self.assertTrue(train and test)
        self.assertLess(max(r["match_date"] for r in train), cutoff)
        self.assertGreaterEqual(min(r["match_date"] for r in test), cutoff)
        self.assertEqual(len(train) + len(test), 30)

    def test_three_way_date_boundaries(self):
        rows = [
            {"match_id": str(i), "match_date": f"2026-01-{i//2+1:02d}", "outcome": i % 2}
            for i in range(50)
        ]
        train, validation, final_test, first, second = chronological_three_way_split(rows)
        self.assertEqual(len(train) + len(validation) + len(final_test), 50)
        self.assertTrue(train and validation and final_test)
        self.assertLess(max(r["match_date"] for r in train), first)
        self.assertLess(max(r["match_date"] for r in validation), second)
        self.assertGreaterEqual(min(r["match_date"] for r in final_test), second)

    def test_three_way_requires_three_dates(self):
        rows = [{"match_id": str(i), "match_date": f"2026-01-{i+1:02d}"} for i in range(2)]
        with self.assertRaisesRegex(ValueError, "enough distinct dates"):
            chronological_three_way_split(rows)

    def test_fractional_labels_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_binary_baseline(
                [{"outcome": 0.5}] * 100, [{"outcome": 1}], "outcome")

    def test_duplicate_rejected(self):
        rows = [{"match_id": "a", "match_date": "2026-01-01"},
                {"match_id": "a", "match_date": "2026-01-02"}]
        with self.assertRaises(ValueError):
            chronological_split(rows)

    def test_baseline_uses_training_only(self):
        train = [{"outcome": 1} for _ in range(100)]
        test = [{"outcome": 0} for _ in range(20)]
        report = evaluate_binary_baseline(train, test, "outcome")
        self.assertEqual(report["train_rate"], 1)
        self.assertEqual(report["test_rate"], 0)
        self.assertEqual(report["test_brier"], 1)

    def test_invalid_binary_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_binary_baseline([{"outcome": 2}] * 100, [{"outcome": 0}], "outcome")


if __name__ == "__main__":
    unittest.main()
