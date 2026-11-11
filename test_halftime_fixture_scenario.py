"""Dependency-free regression checks for halftime Poisson scenario."""
import unittest
from math import exp
from halftime_fixture_scenario import second_half_scenario

class ScenarioChecks(unittest.TestCase):
    def test_goal_race_is_exhaustive(self):
        r=second_half_scenario(1.8,1.2,0.8,0.3,1,0)
        p=r["probabilities"]
        self.assertAlmostEqual(p["Home scores first in 2H (model)"]+
            p["Away scores first in 2H (model)"]+p["No second-half goal"],1,places=10)
        self.assertAlmostEqual(p["Home wins FT"]+p["Draw FT"]+p["Away wins FT"],1,places=10)
        self.assertAlmostEqual(p["Home wins 2H"]+p["Draw 2H"]+p["Away wins 2H"],1,places=10)

    def test_symmetric_case(self):
        p=second_half_scenario(1.4,1.4,0.4,0.4,0,0)["probabilities"]
        self.assertAlmostEqual(p["Home scores first in 2H (model)"],
                               p["Away scores first in 2H (model)"])
        self.assertAlmostEqual(p["Home wins FT"],p["Away wins FT"])

    def test_zero_goal_rates(self):
        p=second_half_scenario(0,0,0,0,0,0)["probabilities"]
        self.assertEqual(p["No second-half goal"],1)
        self.assertEqual(p["Draw FT"],1)

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            second_half_scenario(-1,1,0,0,0,0)
        with self.assertRaises(ValueError):
            second_half_scenario(1,1,0,0,0,0,remaining_share=1.0)

if __name__=="__main__":
    unittest.main()
