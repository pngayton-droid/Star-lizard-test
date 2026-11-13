import unittest
from datetime import date
from research.opponent_strength import predict,fit_strengths

class OpponentStrengthTests(unittest.TestCase):
    def test_no_future_information(self):
        d=date(2026,1,1)
        old=[dict(date=date(2025,1,1),home_team="A",away_team="B",home_xg=2.,away_xg=.5)]
        future=dict(date=date(2026,2,1),home_team="A",away_team="B",home_xg=50.,away_xg=0.)
        self.assertEqual(predict(old,"A","B",d),predict(old+[future],"A","B",d))
    def test_finite_probabilities(self):
        d=date(2026,1,1)
        matches=[dict(date=date(2025,1,1),home_team="A",away_team="B",home_xg=2.,away_xg=.5)]
        h,a=predict(matches,"A","B",d)
        self.assertGreater(h,0)
        self.assertGreater(a,0)
    def test_empty_history(self):
        self.assertEqual(predict([],"A","B",date(2026,1,1)),(1.5,1.2))
if __name__=="__main__":
    unittest.main()
