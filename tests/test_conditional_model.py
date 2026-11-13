"""Offline tests for categorical shrinkage model."""
import unittest
from research.conditional_model import smoothed_rate, fit_conditional_rates, predict, evaluate, calibration_bins


class ConditionalModelTests(unittest.TestCase):
    def test_shrinkage(self):
        self.assertAlmostEqual(smoothed_rate(2, 2, .5, 8), .6)
        self.assertEqual(smoothed_rate(0, 0, .25, 20), .25)

    def test_unseen_group_uses_training_prior(self):
        train = [{"league": "A", "outcome": 1} for _ in range(10)]
        train += [{"league": "B", "outcome": 0} for _ in range(10)]
        model = fit_conditional_rates(train, ["league"], "outcome")
        p, n = predict(model, {"league": "C"})
        self.assertEqual(n, 0)
        self.assertEqual(p, .5)

    def test_test_outcomes_never_affect_prediction(self):
        train = [{"state": "draw", "outcome": 1} for _ in range(20)]
        model = fit_conditional_rates(train, ["state"], "outcome")
        first = evaluate(model, [{"state": "draw", "outcome": 0}], "outcome")
        second = evaluate(model, [{"state": "draw", "outcome": 1}], "outcome")
        self.assertEqual(first["predicted_rate"], second["predicted_rate"])
        self.assertNotEqual(first["model_brier"], second["model_brier"])

    def test_calibration_bins_use_fixed_predictions(self):
        training = [{"group": "A", "outcome": 1}, {"group": "B", "outcome": 0}]
        model = fit_conditional_rates(training, ["group"], "outcome", 0)
        validation = [{"group": "A", "outcome": 0}, {"group": "B", "outcome": 1}]
        bins = calibration_bins(model, validation, "outcome", 5)
        self.assertEqual(sum(x["Matches"] for x in bins), 2)
        self.assertEqual([x["Predicted %"] for x in bins], [0.0, 100.0])
        self.assertEqual([x["Observed %"] for x in bins], [100.0, 0.0])

    def test_invalid_counts(self):
        with self.assertRaises(ValueError):
            smoothed_rate(3, 2, .5)


if __name__ == "__main__":
    unittest.main()
