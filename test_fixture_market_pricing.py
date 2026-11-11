"""Regression tests for the shared fixture goals research pricing engine."""
import unittest
from math import exp
from fixture_market_pricing import price_goals

class FixtureMarketPricingTests(unittest.TestCase):
    def test_symmetric_match(self):
        result=price_goals(1.4,1.4)
        p=result["probabilities"]
        self.assertAlmostEqual(p["home_win"],p["away_win"],places=10)
        self.assertAlmostEqual(p["home_win"]+p["draw"]+p["away_win"]+result["missing_mass"],1,places=10)
        self.assertAlmostEqual(p["over_2_5"]+p["under_2_5"],1)
        self.assertAlmostEqual(p["btts_yes"]+p["btts_no"],1)
        self.assertLess(result["missing_mass"],1e-8)
    def test_no_goal_case(self):
        p=price_goals(0,0)["probabilities"]
        self.assertAlmostEqual(p["draw"],1)
        self.assertAlmostEqual(p["under_2_5"],1)
        self.assertAlmostEqual(p["btts_yes"],0)
    def test_analytic_total(self):
        p=price_goals(1.0,1.5)["probabilities"]
        self.assertAlmostEqual(p["under_1_5"],exp(-2.5)*3.5)
    def test_reject_invalid_intensities(self):
        for h,a in [(-1,1),(float("nan"),1),(1,float("inf"))]:
            with self.assertRaises(ValueError):price_goals(h,a)
    def test_correct_score_order(self):
        scores=price_goals(1.2,.9)["top_scores"]
        self.assertEqual(len(scores),8)
        self.assertTrue(all(scores[i]["probability"]>=scores[i+1]["probability"] for i in range(7)))

if __name__=="__main__":
    unittest.main()
