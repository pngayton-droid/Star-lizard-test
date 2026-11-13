import math
import unittest
from datetime import date, timedelta
from research.independent_pricing import probabilities, walk_forward

class PricingTests(unittest.TestCase):
    def test_probabilities(self):
        for a,b in ((1.4,1.1),(2.5,.6),(.4,.4)):
            p=probabilities(a,b)
            self.assertAlmostEqual(sum(p),1,places=8)
            self.assertTrue(all(0<=x<=1 for x in p))
    def test_home_advantage(self):
        p=probabilities(2,1)
        self.assertGreater(p[0],p[2])
    def test_same_day_not_leaked(self):
        day=date(2026,1,1)
        rows=[dict(date=day+timedelta(days=i),home_team="A",away_team="B",
                   home_goals=1,away_goals=0,home_xg=1.4,away_xg=.7) for i in range(4)]
        results=walk_forward(rows,minimum_train=2)
        self.assertEqual(len(results),2)

if __name__=="__main__":
    unittest.main()
