"""Tests for fixture venue xG baseline input validation."""
import unittest
from fixture_goals_baseline import baseline

class FixtureGoalsBaselineTests(unittest.TestCase):
    def setUp(self):
        self.fixture={"competition_id":"3039","home_team":{"name":"Home FC"},
                      "away_team":{"name":"Away FC"}}
        self.rows=[
            {"competition_id":"3039","team_name":"Home FC","venue":"home","sample_n":12,
             "xg_for_avg":1.8,"xg_against_avg":1.2,"last_match_date":"2026-11-01"},
            {"competition_id":"3039","team_name":"Away FC","venue":"away","sample_n":11,
             "xg_for_avg":1.4,"xg_against_avg":1.0,"last_match_date":"2026-10-30"}]
    def test_valid_baseline(self):
        result=baseline(self.fixture,self.rows)
        self.assertAlmostEqual(result["home_xg"],1.4)
        self.assertAlmostEqual(result["away_xg"],1.3)
        self.assertTrue(0<result["over_2_5"]<1)
    def test_reject_nan(self):
        self.rows[0]["xg_for_avg"]=float("nan")
        self.assertIsNone(baseline(self.fixture,self.rows))
    def test_reject_infinity(self):
        self.rows[1]["xg_against_avg"]=float("inf")
        self.assertIsNone(baseline(self.fixture,self.rows))
    def test_reject_malformed(self):
        self.rows[0]["xg_for_avg"]="unavailable"
        self.assertIsNone(baseline(self.fixture,self.rows))
    def test_reject_low_sample(self):
        self.rows[1]["sample_n"]=7
        self.assertIsNone(baseline(self.fixture,self.rows))
    def test_reject_ambiguous_team(self):
        self.rows.append(dict(self.rows[0]))
        self.assertIsNone(baseline(self.fixture,self.rows))

if __name__=="__main__":unittest.main()
